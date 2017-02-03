import sys
import json
import urllib2
from datetime import datetime
from dateutil import parser
from pytz import utc
from influxdb import InfluxDBClient

TIMESTAMP = datetime.now().isoformat()

def getConfig():
    with open (sys.path[0] + '/../config/config.json', 'r') as configfile:
        return json.loads(configfile.read())
    sys.stderr.write('%s\tProblem reading config file.\n' % TIMESTAMP)
    sys.exit(1)

PURPLE_AIR_VALUES = {
    'Latitude': 'Lat',
    'Longitude': 'Lon',
    'Pressure (Pa)': 'pressure',
    'Humidity (%)': 'humidity',
    'Temp (*C)': 'temp_f',  # this gets converted specifically in the function
    'pm2.5 (ug/m^3)': 'PM2_5Value'
}

PURPLE_AIR_TAGS = {
    'ID': 'ID',
    'Sensor Model': 'Type'
}

def uploadPurpleAirData(client):
    try:
        purpleAirData = urllib2.urlopen("https://map.purpleair.org/json").read()
    except URLError:
        sys.stderr.write('%s\tProblem acquiring PurpleAir data; their server appears to be down.\n' % TIMESTAMP)
        return []

    purpleAirData = unicode(purpleAirData, 'ISO-8859-1')
    purpleAirData = json.loads(purpleAirData)['results']
    for measurement in purpleAirData:
        point = {
            'measurement': 'airQuality',
            'fields': {},
            'tags': {
                'Source': 'Purple Air'
            }
        }
        # Figure out the time stamp
        try:
            point['time'] = datetime.fromtimestamp(measurement['LastSeen'], tz=utc)
        except TypeError:
            continue    # don't include the point if we can't parse the timestamp

        # Attach the tags - values about the station that shouldn't change across measurements
        for standardKey, purpleKey in PURPLE_AIR_TAGS.iteritems():
            if measurement.has_key(purpleKey):
                point['tags'][standardKey] = measurement[purpleKey]

        if not point['tags'].has_key('ID'):
            continue    # don't include the point if it doesn't have an ID
        # prefix the ID with "Purple Air " so that there aren't collisions with other data sources
        point['tags']['ID'] = 'Purple Air %i' % point['tags']['ID']

        # Only include the point if we haven't stored this measurement before
        lastPoint = client.query("""SELECT last("Temp (*C)") FROM airQuality WHERE "ID" = '%s'""" % point['tags']['ID'])
        if len(lastPoint) > 0:
            lastPoint = lastPoint.get_points().next()
            if point['time'] <= parser.parse(lastPoint['time']):
                continue

        # Convert all the fields to floats
        for standardKey, purpleKey in PURPLE_AIR_VALUES.iteritems():
            if measurement.has_key(purpleKey):
                try:
                    point['fields'][standardKey] = float(measurement[purpleKey])
                except (ValueError, TypeError):
                    pass    # just leave bad / missing values blank

        # Convert the purple air deg F to deg C
        if point['fields'].has_key('Temp (*C)'):
            point['fields']['Temp (*C)'] = (point['fields']['Temp (*C)'] - 32) * 5 / 9

        client.write_points([point])


if __name__ == '__main__':
    config = getConfig()
    client = InfluxDBClient('127.0.0.1', 8086, config['influxdbUsername'], config['influxdbPassword'], 'defaultdb')
    uploadPurpleAirData(client)
    sys.stdout.write('%s\tPolling successful.\n' % TIMESTAMP)