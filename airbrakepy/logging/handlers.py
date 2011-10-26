import inspect
import logging
import traceback
import multiprocessing
import urllib2
import sys
import xmlbuilder
from airbrakepy import __version__ ,__source_url__, __app_name__

_POISON = "xxxxPOISONxxxx"

class AirbrakeSender(multiprocessing.Process):
    def __init__(self, work_queue, timeout_in_ms, service_url):
        multiprocessing.Process.__init__(self, name="AirbrakeSender")
        self.work_queue = work_queue
        self.timeout_in_seconds = timeout_in_ms / 1000.0
        self.service_url = service_url

    def _handle_error(self):
        ei = sys.exc_info()
        try:
            traceback.print_exception(ei[0], ei[1], ei[2],
                                      file=sys.stderr)
        except IOError:
            pass
        finally:
            del ei

    def run(self):
        global _POISON
        while True:
            try:
                message = self.work_queue.get()
                if message == _POISON:
                    break
                self._sendMessage(message)
            except Exception:
                self._handle_error()

    def _sendHttpRequest(self, headers, message):
        request = urllib2.Request(self.service_url, message, headers)
        try:
            response = urllib2.urlopen(request, timeout=self.timeout_in_seconds)
            status = response.getcode()
        except urllib2.HTTPError as e:
            status = e.code
        return status

    def _sendMessage(self, message):
        headers = {"Content-Type": "text/xml"}
        status = self._sendHttpRequest(headers, message)
        if status == 200:
            return

        exceptionMessage = "Unexpected status code {0}".format(str(status))

        if status == 403:
            exceptionMessage = "Unable to send using SSL"
        elif status == 422:
            exceptionMessage = "Invalid XML sent: {0}".format(message)
        elif status == 500:
            exceptionMessage = "Destination server is unavailable. Please check the remote server status."
        elif status == 503:
            exceptionMessage = "Service unavailable. You may be over your quota."

        raise StandardError(exceptionMessage)

_DEFAULT_AIRBRAKE_URL = "http://airbrakeapp.com/notifier_api/v2/notices"

class AirbrakeHandler(logging.Handler):
    def __init__(self, api_key, environment=None, component_name=None, node_name=None,
                 use_ssl=False, timeout_in_ms=30000, airbrake_url=_DEFAULT_AIRBRAKE_URL):
        logging.Handler.__init__(self)
        self.api_key = api_key
        self.environment = environment
        self.component_name = component_name
        self.node_name = node_name
        self.work_queue = multiprocessing.Queue()
        self.work_queue.cancel_join_thread()
        self.worker = AirbrakeSender(self.work_queue, timeout_in_ms, self._serviceUrl(airbrake_url, use_ssl))
        self.worker.start()
        self.logger = logging.getLogger(__name__)

    def emit(self, record):
        try:
            message = self._generate_xml(record)
            self.work_queue.put(message)
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("Airbrake message queued for delivery")
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


    def close(self):
        if self.work_queue:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("POISONING QUEUE")
            global _POISON
            self.work_queue.put(_POISON, False)
            self.work_queue.close()
            self.work_queue = None

        if self.worker:
            self.logger.info("Waiting for remaining items to be sent to Airbrake.")
            self.worker.join(timeout=5.0)
            if self.worker.is_alive():
                self.logger.info("AirbrakeSender did not exit in an appropriate amount of time...terminating")
                self.worker.terminate()
            self.worker = None

        logging.Handler.close(self)

    def _serviceUrl(self, airbrake_url, use_ssl):
        if use_ssl:
            return airbrake_url.replace('http://', 'https://', 1)
        else:
            return airbrake_url.replace('https://', 'http://', 1)

    #
    # This is largely based on the code example presented here:
    #   http://robots.thoughtbot.com/post/323503523/writing-a-hoptoad-notifier-contacting-the-toad
    #
    def _generate_xml(self, record):
        exn = None
        trace = None
        if record.exc_info:
            _, exn, trace = record.exc_info

        message = record.getMessage()

        if exn:
            message = "{0}: {1}".format(message, str(exn))

        xml = xmlbuilder.XMLBuilder()
        with xml.notice(version=2.0):
            xml << ('api-key', self.api_key)
            with xml.notifier:
                xml << ('name', __app_name__)
                xml << ('version', __version__)
                xml << ('url', __source_url__)
            with xml('server-environment'):
                xml << ('environment-name', self.environment)
            with xml.request:
                xml << ("url", "")
                xml << ("component", self.component_name)
                with xml("cgi-data"):
                    with xml("var", key="nodeName"):
                        xml << self.node_name
                    with xml("var", key="componentName"):
                        xml << self.component_name
            with xml.error:
                xml << ('class', '' if exn is None else exn.__class__.__name__)
                xml << ('message', message)
                with xml.backtrace:
                    if trace is None:
                        [xml << ('line', {'file': record.pathname, 'number': record.lineno, 'method': record.funcName})]
                    else:
                        [xml << ('line', {'file': filename, 'number': line_number, 'method': "{0}: {1}".format(function_name, text)})\
                         for filename, line_number, function_name, text in traceback.extract_tb(trace)]
        return str(xml)

