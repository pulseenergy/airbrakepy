import logging
import ConfigParser
import os
from airbrakepy.logging.handlers import AirbrakeHandler

if __name__=='__main__':
    configFilePath = os.path.join(os.path.expanduser("~"), ".airbrakepy")
    print(configFilePath)
    parser = ConfigParser.SafeConfigParser()
    parser.read(configFilePath)
    api_key = parser.get("airbrake", "api_key")
    logging.basicConfig()
    logger = logging.getLogger("test-logger")
    handler = AirbrakeHandler(api_key, environment='dev', component_name='integration-test', node_name='server')
    logger.addHandler(handler)

    logger.error("before exception")

    try:
        raise Exception('bam, pow')
    except Exception as e:
        logger.error("test with exception", exc_info=True)

    logger.error("after exception")

    for i in range(20):
        logger.error("logging error %d", i)
