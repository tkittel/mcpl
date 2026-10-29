
################################################################################
##                                                                            ##
##  This file is part of MCPL (see https://mctools.github.io/mcpl/)           ##
##                                                                            ##
##  Copyright 2015-2026 MCPL developers.                                      ##
##                                                                            ##
##  Licensed under the Apache License, Version 2.0 (the "License");           ##
##  you may not use this file except in compliance with the License.          ##
##  You may obtain a copy of the License at                                   ##
##                                                                            ##
##      http://www.apache.org/licenses/LICENSE-2.0                            ##
##                                                                            ##
##  Unless required by applicable law or agreed to in writing, software       ##
##  distributed under the License is distributed on an "AS IS" BASIS,         ##
##  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  ##
##  See the License for the specific language governing permissions and       ##
##  limitations under the License.                                            ##
##                                                                            ##
################################################################################


"""Messages and warnings to the user, printed or sent to the logger "mcpl"."""

__all__ = ['use_logging']

import threading

_logger = None

def use_logging( enable = True ):
    """Send messages and warnings from MCPL to the logger named "mcpl" (as
    logging.INFO and logging.WARNING records), instead of printing them to
    stdout (prefixed with "MCPL:" and "MCPL WARNING:"), which is the default.
    After that, they are controlled by the logging configuration of the
    application, e.g.:

       import logging
       import mcpl
       mcpl.use_logging()
       logging.basicConfig(level=logging.INFO)

    Calling use_logging(False) switches back to printing. Note that this does
    not affect functions which are meant to print (like dump_file), nor the
    mcpltool command, which always prints."""
    global _logger
    if enable:
        import logging
        _logger = logging.getLogger('mcpl')
    else:
        _logger = None

class _ForcePrinting:
    """Context manager for printing messages, even if use_logging() was
    called."""
    def __enter__(self):
        global _logger
        self._orig, _logger = _logger, None
    def __exit__(self, *args):
        global _logger
        _logger = self._orig

class _CollectMessages:
    """Context manager collecting the messages of the current thread (in the
    list lines) instead of printing or logging them, without affecting other
    threads (unlike redirecting sys.stdout)"""
    def __enter__(self):
        self.lines, self._orig = [], getattr(_collecting,'lines',None)
        _collecting.lines = self.lines
        return self
    def __exit__(self, *args):
        _collecting.lines = self._orig

_collecting = threading.local()

def _emit( text, log, msg ):
    lines = getattr(_collecting,'lines',None)
    if lines is not None:
        lines.append(text)
    elif _logger is None:
        print(text)
    else:
        log(msg)

def _info( msg, prefix = 'MCPL: ' ):
    _emit(f'{prefix}{msg}',_logger and _logger.info,msg)

def _warning( msg ):
    _emit(f'MCPL WARNING: {msg}',_logger and _logger.warning,msg)

def _error( msg ):
    _emit(f'MCPL ERROR: {msg}',_logger and _logger.error,msg)
