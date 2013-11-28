from PIL import Image
from pycoast import ContourWriter
from pyresample import image, geometry
import numpy as np
from collections import namedtuple
import requests
from os import environ, path
from StringIO import StringIO
import datetime

plot_debug = True
    
def findStartIndex(img):
    """Return the first row index not containing the white border at the top"""

    look  = False
    start = 3
    i = start
    left  = 10
    right = img.shape[0] - 10
    for r in img[start:]:
        m = np.amin(r[left:right])
#        print m
        if (look and m < 255):
            return i
        elif (not look and m == 255):
            look = True
        i = i + 1
    return 0

def cut_borders(data):
    """Remove the white border of a satellite images (including text)"""

    x1 = findStartIndex(data)
    data = data[x1:,:]
    data = data[::-1]
    x2 = findStartIndex(data)
    data = data[x2:,:]
    data = data[::-1]

    data = data.T
    x1 = findStartIndex(data)
    data = data[x1:,:]
    data = data[::-1]
    x2 = findStartIndex(data)
    data = data[x2:,:]
    data = data[::-1]
    return data.T

def project(satellite):
    """Reproject the satellite image on an equirectangular map"""
    
    img = Image.open(satellite.filename).convert("L")
    data = np.array(img)
    data = cut_borders(data)

    x_size = data.shape[1]
    y_size = data.shape[0]
    proj_dict = {'a': '6378169.0', 'b': '6356584.0',
                 'lon_0': satellite.longitude,
                 'y_0': satellite.false_y,
                 'h': '35785831.0', 'proj': 'geos'}
    area_extent =(-satellite.extent, -satellite.extent,
                  satellite.extent, satellite.extent)
    area = geometry.AreaDefinition('geo', 'geostat', 'geo', proj_dict, x_size,
                                   y_size, area_extent)
    dataIC = image.ImageContainerQuick(data, area)

    proj_dict = {'proj': 'eqc'}
    area_extent =(-20037508.34, -10018754.17, 20037508.34, 10018754.17)
    x_size = 2048
    y_size = 1024
    pc = geometry.AreaDefinition('pc', 'Plate Carree world map', 'pc',
                                 proj_dict, x_size, y_size, area_extent)

    #msg_con_nn = image.ImageContainerNearest(data, area, radius_of_influence=50000)
    dataResampled = dataIC.resample(pc)
    dataResampledImage = satellite.rescale(dataResampled.image_data)

    dataResampledImage[0:90, :] = dataResampledImage[180:90:-1, :]
    dataResampledImage[1024-90:1024, :] = dataResampledImage[1024-90:1024-180:-1, :]

    width = 55
    weight = np.array([max((width - min([abs(satellite.longitude - x),
                                         abs(satellite.longitude - x + 360),
                                         abs(satellite.longitude - x - 360)]))/180,
                           1e-7) for x in np.linspace(-180, 180, dataResampled.shape[1])])
    return np.array([dataResampledImage, np.tile(weight, (dataResampled.shape[0], 1))])

def saveImage(new_image, filename, overlays = False):
    """Save satellite image"""

    rgbArray = np.zeros((new_image.shape[0], new_image.shape[1], 3), 'uint8')
    rgbArray[..., 0] = new_image
    rgbArray[..., 1] = new_image
    rgbArray[..., 2] = new_image
    img = Image.fromarray(rgbArray)

    if overlays:
        proj4_string = '+proj=eqc'
        area_extent = (-20037508.34, -10018754.17, 20037508.34, 10018754.17)
        area_def = (proj4_string, area_extent)
        cw = ContourWriter('./gshhg')
        cw.add_coastlines(img, area_def, outline = 'red', resolution='l', level=4)
        cw.add_grid(img, area_def, (20, 20), (10, 10), outline = 'blue')

    img.save(filename)

def curve(b):
    """Rescale the brightness values used for MTSAT2 satellite"""
    return np.minimum(b*255.0/193.0, 255)

def ID(b):
    """Identity function"""
    return b

class SatelliteData:
    def __init__(self, longitude, extent, false_y, rescale, base_url, suffix):
        self.longitude = longitude
        self.extent    = extent
        self.false_y   = false_y
        self.rescale   = rescale
        self.base_url  = base_url
        self.suffix    = suffix
        
    def set_time(self, dt):
        self.dt = datetime.datetime(dt.year, dt.month, dt.day, dt.hour/3*3, 0, 0)
        str1 = self.dt.strftime("%Y/%m/%d/%H00/")
        str2 = self.dt.strftime("%Y_%m_%d_%H00")
        self.url      = self.base_url + str1 + str2 + self.suffix
        self.filename = str2 + self.suffix
    
    def check_for_image(self):
        username = environ['SATUSER']
        passwd   = environ['SATPASSWD']
        
        if path.isfile(self.filename):
            return True
        r = requests.head(self.url, auth=(username, passwd))
        if r.status_code == requests.codes.ok:
            return True
        else:
            return False
            
    def download_image(self):
        username = environ['SATUSER']
        passwd   = environ['SATPASSWD']
        
        if path.isfile(self.filename):
            return
        r = requests.get(self.url, auth=(username, passwd))
        i = Image.open(StringIO(r.content))
        i.save(self.filename)
         

images = []

satellite_list = (
                  SatelliteData(145.0, 5433878.562*1.01, 50000,
                                curve,
                                "http://www.sat.dundee.ac.uk/xrit/145.0E/MTSAT/",
                                "_MTSAT2_4_S1.jpeg"
                                ),
                  SatelliteData(57.0, 5568742.4*0.97, 0,
                                ID,
                                "http://www.sat.dundee.ac.uk/xrit/057.0E/MET/",
                                "_MET7_2_S1.jpeg"
                                ),
                  SatelliteData(0.0, 5433878.562, 0,
                                ID,
                                "http://www.sat.dundee.ac.uk/xrit/000.0E/MSG/",
                                "_MSG3_9_S1.jpeg"
                                ),
                  SatelliteData(-75.0, 5433878.562, 0,
                                ID,
                                "http://www.sat.dundee.ac.uk/xrit/075.0W/GOES/",
                                "_GOES13_4_S1.jpeg"
                                ),
                  SatelliteData(-135.0, 5433878.562, 0,
                                ID,
                                "http://www.sat.dundee.ac.uk/xrit/135.0W/GOES/",
                                "_GOES15_4_S1.jpeg"
                                ),
                  )

dt = datetime.datetime.utcnow()
max_tries = 10

for _ in range(max_tries):
    found_all = True

    for satellite in satellite_list:
        satellite.set_time(dt)
        found_all &= satellite.check_for_image()
        
    if found_all: break
    dt = dt - datetime.timedelta(hours = 3)
    
print "Download image date/time: ", satellite_list[0].dt.strftime("%Y-%m-%d %H:00 UTC")

i = 1
for satellite in satellite_list:
    print "Satellite file: ", satellite.filename
    satellite.download_image()
    img = project(satellite)
    if plot_debug: saveImage(img[0], "test" + `i` + ".jpeg", overlays=True)
    if plot_debug: saveImage(np.array(img[1]*255, 'uint8'), "weighttest" + `i` + ".jpeg", overlays=True)
    images.append(img)
    i += 1

images = np.array(images)

weight_sum = np.sum(images[:, 1], axis = 0)
if plot_debug: saveImage(np.array(weight_sum*255, 'uint8'), "weightsum.jpeg", overlays=True)
new_image = np.sum(images[:, 0] * images[:, 1], axis = 0)/weight_sum

saveImage(new_image, "clouds_2048.jpg")
if plot_debug: saveImage(new_image, "test.jpeg", overlays=True)
print "finished"