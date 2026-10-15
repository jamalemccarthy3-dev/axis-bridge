"""domain_hub_server.py - ONE domain hub as its own local server:  python domain_hub_server.py sports|markets|logistics|economics

A hub process serves exactly one domain, on its own loopback port (NEXXUS_PORT_<DOMAIN>, see domain_dispatch.py). Its chat is the same gated, prompt-locked, output-filtered chat the portal
windows use (portal_chat.py), and it has its own history. It refuses any message addressed to another domain, so even a mis-routed request cannot get an answer from the wrong hub.
Listens on 127.0.0.1 only.
"""
import os
import sys

from flask import Flask, jsonify, request

import domain_dispatch
import portal_chat
import portals


def make_app(domain):
    if domain not in portals.ORDER:
        raise SystemExit("usage: python domain_hub_server.py %s" % "|".join(portals.ORDER))
    app = Flask("nexxus_hub_" + domain)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "success", "domain": domain, "port": domain_dispatch.port(domain), "web_search": portal_chat.web_enabled()})

    @app.route("/chat", methods=["POST"])
    def chat():
        d = request.get_json(silent=True)
        if not isinstance(d, dict) or not isinstance(d.get("message"), str):
            return jsonify({"status": "error", "message": "send {\"message\": \"...\"}"}), 400
        if d.get("portal", domain) != domain:                                          # hard isolation: this process is the %s hub and nothing else
            return jsonify({"status": "error", "message": "this is the %s hub; it does not serve %r" % (domain, d.get("portal"))}), 400
        res = portal_chat.chat(domain, d["message"])
        return jsonify(dict(res, status="busy" if res["kind"] == "busy" else "success")), (429 if res["kind"] == "busy" else 200)

    @app.route("/reset", methods=["POST"])
    def reset():
        portal_chat.reset(domain)
        return jsonify({"status": "success", "domain": domain})

    return app


if __name__ == "__main__":
    dom = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    app = make_app(dom)
    p = domain_dispatch.port(dom)
    print("[HUB %s] listening on 127.0.0.1:%d" % (dom.upper(), p))
    app.run(host="127.0.0.1", port=p, threaded=True, debug=False, use_reloader=False)
