import logging
import ConfigParser
import os
import time
from airbrakepy.logging.handlers import AirbrakeHandler

def method_three():
    raise StandardError('bam, pow')


def method_two():
    method_three()


def method_one():
    method_two()

if __name__=='__main__':
    configFilePath = os.path.join(os.path.expanduser("~"), ".airbrakepy")
    print(configFilePath)
    parser = ConfigParser.SafeConfigParser()
    parser.read(configFilePath)
    api_key = parser.get("airbrake", "api_key")
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("test-logger")
    handler = AirbrakeHandler(api_key, environment='dev', component_name='integration-test', node_name='server')
    logger.addHandler(handler)

    logger.error("before exception")

    try:
        method_one()
    except StandardError:
        logger.error("test with exception", exc_info=True)
        logger.error("test without exception", exc_info=False)

    logger.error("after exception")

    logging.shutdown()