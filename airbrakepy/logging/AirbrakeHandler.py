from Queue import Queue
import logging
import traceback
import urllib2
import xmlbuilder
from airbrakepy import __version__ ,__source_url__, __app_name__
from threading import Thread

_NOTIFIER_NAME = 'AirbrakePy'
_DEFAULT_AIRBRAKE_URL = 'http://airbrakeapp.com/notifier_api/v2/notices'
_POISON = "xxxxPOISONxxxx"

class AirbrakeSender(Thread):
    def __init__(self, work_queue, timeout_in_ms, service_url):
        Thread.__init__(self)
        self.work_queue = work_queue
        self.timeout_in_seconds = timeout_in_ms / 1000.0
        self.service_url = service_url

    def run(self):
        while True:
            try:
                message = self.work_queue.get()
                if message is _POISON:
                    break
                self._sendMessage(message)
            except Exception as e:
                print("{0}: {1}".format(e.__class__.__name__, str(e)))

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

        raise Exception(exceptionMessage)


class AirbrakeHandler(logging.Handler):
    def __init__(self, api_key, environment=None, component_name=None, node_name=None, timeout_in_ms=30000,
                 use_ssl=False, airbrake_url=_DEFAULT_AIRBRAKE_URL):
        logging.Handler.__init__(self)
        self.api_key = api_key
        self.environment = environment
        self.component_name = component_name
        self.node_name = node_name
        self.work_queue = Queue()
        self.worker = AirbrakeSender(self.work_queue, timeout_in_ms, self._serviceUrl(airbrake_url, use_ssl))
        self.worker.setDaemon(True)
        self.worker.start()

    def emit(self, record):
        message = self._generate_xml(record)
        self.work_queue.put(message)

    def close(self):
        self.work_queue.put(_POISON, False)
        self.worker.join(timeout=5.0)
        if self.worker.isAlive():
            print "AirbrakeSender did not exit in an appropriate amount of time...terminating"

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
        if not record.exc_info is None:
            _, exn, trace = record.exc_info

        xml = xmlbuilder.XMLBuilder()
        with xml.notice(version=2.0):
            xml << ('api-key', self.api_key)
            with xml.notifier:
                xml << ('name', __app_name__)
                xml << ('version', __version__)
                xml << ('url', __source_url__)
            with xml('server-environment'):
                xml << ('environment-name', self.environment)
            with xml.error:
                xml << ('class', '' if exn is None else exn.__class__.__name__)
                xml << ('message', record.msg if exn is None else "{0}: {1}".format(record.msg, str(exn)))
                with xml.backtrace:
                    if trace is None:
                        [xml << ('line', {'file': '', 'number': '', 'method': ''})]
                    else:
                        [xml << ('line', {'file': filename, 'number': line_number, 'method': function_name})\
                         for filename, line_number, function_name, _ in traceback.extract_tb(trace)]

        return str(xml)

