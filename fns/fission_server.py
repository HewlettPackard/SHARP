#!/usr/bin/env python
# type: ignore
"""
This Python file is imported from the Fission Python environment source code.

Original Source: https://github.com/fission/environments/blob/master/python/server.py
"""

import importlib
import logging
import os
import signal
import sys
import json

from flask import Flask, request, abort
from gevent.pywsgi import WSGIServer
import bjoern
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from flask_sockets import Sockets

IS_PY2 = sys.version_info.major == 2
SENTRY_DSN = os.environ.get("SENTRY_DSN", None)
SENTRY_RELEASE = os.environ.get("SENTRY_RELEASE", None)
USERFUNCVOL = os.environ.get("USERFUNCVOL", "/userfunc")
RUNTIME_PORT = int(os.environ.get("RUNTIME_PORT", "8888"))

if SENTRY_DSN:
    params = {"dsn": SENTRY_DSN, "integrations": [FlaskIntegration()]}
    if SENTRY_RELEASE:
        params["release"] = SENTRY_RELEASE
    sentry_sdk.init(**params)


def import_src(path):
    """Import soource."""
    if IS_PY2:
        import imp

        return imp.load_source("mod", path)
    else:
        # the imp module is deprecated in Python3. use importlib instead.
        return importlib.machinery.SourceFileLoader("mod", path).load_module()


def store_specialize_info(state):
    """Store specialize info."""
    json.dump(state, open(os.path.join(USERFUNCVOL, "state.json"), "w"))


def check_specialize_info_exists():
    """Check that specialize info exists."""
    return os.path.exists(os.path.join(USERFUNCVOL, "state.json"))


def read_specialize_info():
    """Read specialize info."""
    return json.load(open(os.path.join(USERFUNCVOL, "state.json")))


def remove_specialize_info():
    """Remove specialize info."""
    os.remove(os.path.join(USERFUNCVOL, "state.json"))


class SignalExit(SystemExit):
    """SignalExit class."""

    def __init__(self, signo, exccode=1):
        """Initialize."""
        super(SignalExit, self).__init__(exccode)
        self.signo = signo


def register_signal_handlers(signal_handler=signal.SIG_DFL):
    """Register signal handlers."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


class FuncApp(Flask):
    """FuncApp class."""

    def __init__(self, name, loglevel=logging.DEBUG):
        """Initialize."""
        super(FuncApp, self).__init__(name)

        # init the class members
        self.userfunc = None
        self.root = logging.getLogger()
        self.ch = logging.StreamHandler(sys.stdout)

        #
        # Logging setup.  TODO: Loglevel hard-coded for now. We could allow
        # functions/routes to override this somehow; or we could create
        # separate dev vs. prod environments.
        #
        self.root.setLevel(loglevel)
        self.ch.setLevel(loglevel)
        self.ch.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        self.logger.addHandler(self.ch)

        if check_specialize_info_exists():
            self.logger.info("Found state.json")
            specialize_info = read_specialize_info()
            self.userfunc = self._load_v2(specialize_info)
            self.logger.info("Loaded user function {}".format(specialize_info))

    def load(self):
        """Load user function from codepath."""
        self.logger.info("/specialize called")
        self.userfunc = import_src("/userfunc/user").main
        return ""

    def loadv2(self):
        """Load user function from codepath, v2."""
        specialize_info = request.get_json()
        if check_specialize_info_exists():
            self.logger.warning("Found state.json, overwriting")
        self.userfunc = self._load_v2(specialize_info)
        store_specialize_info(specialize_info)
        return ""

    def healthz(self):
        """Return health status."""
        return "", 200

    def userfunc_call(self, *args):
        """Call user function."""
        if self.userfunc is None:
            self.logger.error("userfunc is None")
            return abort(500)
        return self.userfunc(*args)

    def _load_v2(self, specialize_info):
        filepath = specialize_info["filepath"]
        handler = specialize_info["functionName"]
        self.logger.info(
            'specialize called with  filepath = "{}"   handler = "{}"'.format(
                filepath, handler
            )
        )
        # handler looks like `path.to.module.function`
        parts = handler.rsplit(".", 1)
        if len(handler) == 0:
            # default to main.main if entrypoint wasn't provided
            moduleName = "main"
            funcName = "main"
        elif len(parts) == 1:
            moduleName = "main"
            funcName = parts[0]
        else:
            moduleName = parts[0]
            funcName = parts[1]
        self.logger.debug(
            'moduleName = "{}"    funcName = "{}"'.format(moduleName, funcName)
        )

        # check whether the destination is a directory or a file
        if os.path.isdir(filepath):
            # add package directory path into module search path
            sys.path.append(filepath)

            self.logger.debug('__package__ = "{}"'.format(__package__))
            if __package__:
                mod = importlib.import_module(moduleName, __package__)
            else:
                mod = importlib.import_module(moduleName)

        else:
            # load source from destination python file
            mod = import_src(filepath)

        # load user function from module
        return getattr(mod, funcName)

    def signal_handler(self, signalnum, frame):
        """Handle signals."""
        self.logger.info("Received signal {}".format(signal.strsignal(signalnum)))
        if check_specialize_info_exists():
            self.logger.info("Found state.json, removing")
            remove_specialize_info()
        signal.signal(signalnum, signal.SIG_DFL)
        raise SignalExit(signalnum)


def main():
    """Run server."""
    app = FuncApp(__name__, logging.DEBUG)
    sockets = Sockets(app)
    register_signal_handlers(app.signal_handler)

    app.add_url_rule("/specialize", "load", app.load, methods=["POST"])
    app.add_url_rule("/v2/specialize", "loadv2", app.loadv2, methods=["POST"])
    app.add_url_rule("/healthz", "healthz", app.healthz, methods=["GET"])
    app.add_url_rule(
        "/",
        "userfunc_call",
        app.userfunc_call,
        methods=["GET", "POST", "PUT", "HEAD", "OPTIONS", "DELETE"],
    )
    sockets.add_url_rule(
        "/",
        "userfunc_call",
        app.userfunc_call,
        methods=["GET", "POST", "PUT", "HEAD", "OPTIONS", "DELETE"],
    )

    #
    # TODO: this starts the built-in server, which isn't the most
    # efficient.  We should use something better.
    #
    if os.environ.get("WSGI_FRAMEWORK") == "GEVENT":
        app.logger.info("Starting gevent based server")
        from gevent_ws import WebSocketHandler

        svc = WSGIServer(("0.0.0.0", RUNTIME_PORT), app, handler_class=WebSocketHandler)
        svc.serve_forever()
    else:
        app.logger.info("Starting bjoern based server")
        bjoern.run(app, "0.0.0.0", RUNTIME_PORT, reuse_port=True)


main()
