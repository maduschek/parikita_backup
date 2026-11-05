setTimeout(function () {
    Java.perform(function () {
        console.log("[*] Installing token hooks...");

        try {
            var VolleySingleton = Java.use('dk.assemble.bnet.api.VolleySingleton');
            var setToken = VolleySingleton.setToken.overload('java.lang.String');
            setToken.implementation = function (token) {
                console.log("TOKEN=" + token);
                return setToken.call(this, token);
            };
            console.log("[*] Hooked VolleySingleton.setToken");
        } catch (e) {
            console.log("[!] Could not hook VolleySingleton.setToken: " + e);
        }

        try {
            var NBVars = Java.use('com.assemble.nemborn_shared.initsdk.NBVariables');
            var setSessionToken = NBVars.setSessionToken.overload('java.lang.String');
            setSessionToken.implementation = function (token) {
                console.log("[+] NBVariables.setSessionToken(): " + token);
                return setSessionToken.call(this, token);
            };
            console.log("[*] Hooked NBVariables.setSessionToken");
        } catch (e) {
            console.log("[!] Could not hook NBVariables.setSessionToken: " + e);
        }

        try {
            var SessionTokenRequest = Java.use('dk.assemble.bnet.api.requests.SessionTokenRequest');
            var ctor = SessionTokenRequest.$init.overload(
                'java.lang.String',
                'com.assemble.nemborn_shared.api.volley.Response$ErrorListener',
                'com.assemble.nemborn_shared.api.volley.Response$Listener'
            );
            ctor.implementation = function (url, err, listener) {
                console.log("[*] SessionTokenRequest created for URL: " + url);
                return ctor.call(this, url, err, listener);
            };
            console.log("[*] Hooked SessionTokenRequest constructor");
        } catch (e) {
            console.log("[!] Could not hook SessionTokenRequest constructor: " + e);
        }

        console.log("[*] Hooks installed, Login Now !!!");
    });
}, 1000);
