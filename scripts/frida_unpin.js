// 通用 Android SSL Pinning 绕过（okhttp + conscrypt + 平台 TrustManager）
// 用法: frida -U -f com.eastmoney.android.berlin -l scripts/frida_unpin.js --no-pause

// ---- 第一步：在 APP 代码运行前拦截自杀信号（反调试 kill 防护） ----
try {
    function blockKill(name, signalArgIndex) {
        try {
            var addr = null;
            if (typeof Module.findGlobalExportByName === "function") {
                addr = Module.findGlobalExportByName(name);
            } else if (typeof Module.findExportByName === "function") {
                addr = Module.findExportByName(null, name);
            }
            if (!addr) {
                console.log("[!] 找不到 " + name);
                return;
            }
            Interceptor.attach(addr, {
                onEnter: function (args) {
                    try {
                        var sig = args[signalArgIndex].toInt32();
                        if (sig === 9) {
                            console.log("[+] 拦截 " + name + " SIGKILL");
                            args[signalArgIndex] = ptr(0);
                        }
                    } catch (e) {
                        console.log("[!] onEnter错误: " + e);
                    }
                }
            });
            console.log("[+] 已hook " + name);
        } catch (e) {
            console.log("[!] hook " + name + " 失败: " + e);
        }
    }
    blockKill("kill", 1);
    blockKill("tgkill", 2);
    blockKill("raise", 0);
    blockKill("abort", 0);
    blockKill("exit", 0);
    blockKill("_exit", 0);
    blockKill("exit_group", 0);
    // syscall 包装：SYS_kill=62 SYS_tgkill=131 SYS_tkill=130 SYS_exit_group=231 (x86_64)
    try {
        var syscallFn = Module.findGlobalExportByName("syscall");
        if (syscallFn) {
            Interceptor.attach(syscallFn, {
                onEnter: function (args) {
                    try {
                        var nr = args[0].toInt32();
                        if (nr === 62 || nr === 131 || nr === 130 || nr === 231) {
                            console.log("[+] syscall nr=" + nr + " 被调用");
                            if (nr === 62 || nr === 131 || nr === 130) {
                                // kill/tkill/tgkill: 信号在最后一个参数
                                var sigIdx = nr === 62 ? 2 : (nr === 131 ? 3 : 2);
                                if (args[sigIdx].toInt32() === 9) {
                                    console.log("[+] 拦截 syscall SIGKILL nr=" + nr);
                                    args[sigIdx] = ptr(0);
                                }
                            }
                        }
                    } catch (e) {
                        console.log("[!] syscall onEnter: " + e);
                    }
                }
            });
            console.log("[+] 已hook syscall");
        }
    } catch (e) {
        console.log("[!] syscall hook 失败: " + e);
    }
    console.log("[+] 自杀信号拦截已安装");
} catch (e) {
    console.log("[!] 信号拦截失败: " + e);
}

// ---- 第二步：隐藏 /proc/self/status 中的 TracerPid（反调试检测） ----
try {
    var procFds = {};

    function trackOpen(fnName) {
        var fn = Module.findGlobalExportByName(fnName);
        if (!fn) return;
        Interceptor.attach(fn, {
            onEnter: function (args) {
                try {
                    this.path = args[1].isNull() ? null : args[1].readCString();
                } catch (e) {
                    this.path = null;
                }
            },
            onLeave: function (retval) {
                try {
                    var fd = retval.toInt32();
                    if (this.path && this.path.indexOf("/proc/") === 0 &&
                        this.path.indexOf("status") >= 0 && fd >= 0) {
                        procFds[fd] = this.path;
                    }
                } catch (e) {}
            }
        });
    }
    trackOpen("open");
    trackOpen("open64");
    trackOpen("openat");
    trackOpen("openat64");

    function maskTracerPid(buf, n) {
        try {
            var s = buf.readUtf8String(n);
            var m = s.replace(/TracerPid:\s*(\d+)/g, function (all, digits) {
                return "TracerPid:\t" + "0".repeat(digits.length);
            });
            if (m !== s) {
                buf.writeUtf8String(m);
                console.log("[+] 已伪装 TracerPid");
            }
        } catch (e) {}
    }

    var readFn = Module.findGlobalExportByName("read");
    if (readFn) {
        Interceptor.attach(readFn, {
            onEnter: function (args) {
                this.fd = args[0].toInt32();
                this.buf = args[1];
                this.count = args[2].toInt32();
            },
            onLeave: function (retval) {
                var n = retval.toInt32();
                if (n > 0 && procFds[this.fd] && this.buf) {
                    maskTracerPid(this.buf, n);
                }
            }
        });
    }

    var fgetsFn = Module.findGlobalExportByName("fgets");
    if (fgetsFn) {
        Interceptor.attach(fgetsFn, {
            onEnter: function (args) {
                this.buf = args[0];
                this.size = args[1].toInt32();
            },
            onLeave: function (retval) {
                if (!retval.isNull() && this.buf) {
                    maskTracerPid(this.buf, this.size);
                }
            }
        });
    }

    var freadFn = Module.findGlobalExportByName("fread");
    if (freadFn) {
        Interceptor.attach(freadFn, {
            onEnter: function (args) {
                this.buf = args[0];
                this.size = args[1].toInt32();
                this.nmemb = args[2].toInt32();
            },
            onLeave: function (retval) {
                var n = retval.toInt32() * this.size;
                if (n > 0 && this.buf) {
                    maskTracerPid(this.buf, n);
                }
            }
        });
    }
    console.log("[+] TracerPid 伪装已安装");
} catch (e) {
    console.log("[!] TracerPid 伪装失败: " + e);
}

function waitForJava(callback) {
    if (typeof Java !== "undefined" && Java.available) {
        Java.perform(callback);
    } else {
        setTimeout(function () { waitForJava(callback); }, 200);
    }
}

waitForJava(function () {
    console.log("[+] 开始绕过 SSL Pinning...");

    // 1) SSLContext.init -> 替换为放行所有证书的 TrustManager
    try {
        var SSLContext = Java.use("javax.net.ssl.SSLContext");
        var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
        var PermissiveTrustManager = Java.registerClass({
            name: "com.android.unpin.PermissiveTrustManager",
            implements: [X509TrustManager],
            methods: {
                checkClientTrusted: function (chain, authType) {},
                checkServerTrusted: function (chain, authType) {},
                getAcceptedIssuers: function () { return []; }
            }
        });
        var TrustManagersArray = Java.array(
            "javax.net.ssl.TrustManager",
            [PermissiveTrustManager.$new()]
        );
        SSLContext.init.overload(
            '[Ljavax.net.ssl.KeyManager;',
            '[Ljavax.net.ssl.TrustManager;',
            'java.security.SecureRandom'
        ).implementation = function (keyManager, trustManager, secureRandom) {
            this.init(keyManager, TrustManagersArray, secureRandom);
        };
        console.log("[+] SSLContext.init hooked");
    } catch (e) {
        console.log("[!] SSLContext hook 失败: " + e);
    }

    // 2) okhttp3.CertificatePinner（各版本重载）
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        ["java.lang.String", "java.util.List"].forEach(function (sig) {
            try {
                CertificatePinner.check.overload(sig, "[Ljava.security.cert.Certificate;")
                    .implementation = function () {};
            } catch (e) {}
            try {
                CertificatePinner.check.overload(sig, "java.security.cert.Certificate")
                    .implementation = function () {};
            } catch (e) {}
        });
        ["java.lang.String", "java.util.List"].forEach(function (sig) {
            try {
                CertificatePinner.check.overload(sig, "[Ljava.security.cert.Certificate;")
                    .implementation = function () {};
            } catch (e) {}
        });
        try {
            CertificatePinner.check.overload("java.lang.String", "java.util.List")
                .implementation = function () {};
        } catch (e) {}
        try {
            CertificatePinner.check$okhttp.overload("java.lang.String", "java.util.List")
                .implementation = function () {};
        } catch (e) {}
        console.log("[+] okhttp CertificatePinner hooked");
    } catch (e) {
        console.log("[!] okhttp 未找到: " + e);
    }

    // 3) Android 平台 TrustManagerImpl.verifyChain -> 直接返回未验证链
    try {
        var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
        TrustManagerImpl.verifyChain.overloads.forEach(function (ov) {
            ov.implementation = function () {
                return arguments[0];
            };
        });
        console.log("[+] TrustManagerImpl.verifyChain hooked");
    } catch (e) {
        console.log("[!] TrustManagerImpl 未找到: " + e);
    }

    // 4) checkTrustedRecursive（网络安全配置 pin）
    try {
        var TMImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
        var ArrayList = Java.use("java.util.ArrayList");
        TMImpl.checkTrustedRecursive.overloads.forEach(function (ov) {
            ov.implementation = function () {
                var list = ArrayList.$new();
                try {
                    list.add(arguments[0]);
                } catch (e) {}
                return list;
            };
        });
        console.log("[+] checkTrustedRecursive hooked");
    } catch (e) {
        console.log("[!] checkTrustedRecursive 未找到: " + e);
    }

    console.log("[+] 完成");
});
