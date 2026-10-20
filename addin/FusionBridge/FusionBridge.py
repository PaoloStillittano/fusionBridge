"""FusionBridge add-in entry point.

Starts a localhost HTTP server (fbridge.server) on a background thread. Every request is
handed to Fusion's main thread through a custom event, where fbridge.commands runs it.
"""
import traceback

import adsk.core

from .fbridge import commands, server

EVENT_ID = 'FusionBridge.runJob'

_app = None
_bridge = None
_event = None
_handlers = []  # keep handler references alive, Fusion does not hold them


class _JobHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            _bridge.run_job(args.additionalInfo, commands.dispatch)
        except Exception:
            _app.log('FusionBridge job failed:\n' + traceback.format_exc())


def run(context):
    global _app, _bridge, _event
    _app = adsk.core.Application.get()
    try:
        try:
            _app.unregisterCustomEvent(EVENT_ID)  # left over from a crashed session
        except Exception:
            pass
        _event = _app.registerCustomEvent(EVENT_ID)
        handler = _JobHandler()
        _event.add(handler)
        _handlers.append(handler)

        _bridge = server.Bridge(lambda job_id: _app.fireCustomEvent(EVENT_ID, job_id))
        port = _bridge.start()
        _app.log('FusionBridge listening on 127.0.0.1:%d' % port)
    except Exception:
        _app.userInterface.messageBox('FusionBridge failed to start:\n' + traceback.format_exc())


def stop(context):
    global _bridge, _event
    try:
        if _bridge:
            _bridge.stop()
            _bridge = None
        if _event:
            for handler in _handlers:
                _event.remove(handler)
            _handlers.clear()
            _app.unregisterCustomEvent(EVENT_ID)
            _event = None
    except Exception:
        _app.log('FusionBridge stop error:\n' + traceback.format_exc())
