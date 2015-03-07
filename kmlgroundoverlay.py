#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  kmlgroundoverlay.py
#
#  2015-03-05T13:51:15-0300
#
#  Copyright 2015 Adrien Andre
#
#

from osgeo import gdal
from osgeo import gdalconst

import os
import argparse
import tempfile
import zipfile

from math import *


COMPRESSION = .8
MAX_WIDTH  = 1024
MAX_HEIGHT = 1024




def get_extent(raster):
    cols = raster.RasterXSize
    rows = raster.RasterYSize

    geotransform = raster.GetGeoTransform()
    originX = geotransform[0]
    originY = geotransform[3]
    pixelWidth = geotransform[1]
    pixelHeight = geotransform[5]

    xMax = originX + cols*pixelWidth
    xMin = originX
    yMax = originY
    yMin = originY - rows*pixelHeight

    return (xMax, xMin, yMax, yMin)


def get_size(raster):
    cols = raster.RasterXSize
    rows = raster.RasterYSize

    return (cols, rows)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("src", help="Input")
    parser.add_argument("trg", help="Output")
    args = parser.parse_args()

    src = args.src
    trg = args.trg

    basedir = os.path.dirname(trg) # print basedir
    name = os.path.basename(trg) # print name
    basename = os.path.splitext(name)[0] # print basename

#    # Create temporary output directory
#    out_folder = tempfile.mkdtemp('_tmp', 'gcm_')
#    out_put = os.path.join(str(out_folder), str(in_file))
#    input_file = out_put + ".png"

    # Reproject to WGS84
    target = os.path.join(basedir, "{0}.vrt".format(basename))
    command = "gdalwarp -of VRT -t_srs EPSG:4326 {src} {trg}".format(src = src, trg = target)
    os.system(command)

    # Get extent
    dataset = gdal.Open(target) # print dataset.GetMetadata()
    (east, west, north, south) = get_extent(dataset)
    (width, height) = get_size(dataset) # print width, height

    # Find tile width
    j_max = 1
    while float(width)/float(j_max) > float(MAX_WIDTH):
        j_max = j_max + 1
    tile_width = ceil(float(width)/float(j_max))

    # Find tile height
    i_max = 1
    while float(height)/float(i_max) > float(MAX_HEIGHT):
        i_max = i_max + 1
    tile_height = ceil(float(height)/float(i_max))

    print "Creating {0} tiles ({1}x{2}) of {3}x{4} pixels.".format(i_max*j_max, j_max, i_max, tile_width, tile_height)

    # Build tiles
    # TODO: Define a Tile class
    for i in range(i_max):
        for j in range(j_max):
            source = os.path.join(basedir, "{0}.vrt".format(basename))
            target = os.path.join(basedir, "{0}-{1:0>3d}-{2:0>3d}.jpg".format(basename, i, j))

            command = "gdal_translate -of JPEG -co WORLDFILE=YES -co QUALITY=75 -expand gray -srcwin {xoff:.0f} {yoff:.0f} {xsize:.0f} {ysize:.0f} {src} {trg}".format(xoff = j*tile_width, yoff = i*tile_height, xsize = tile_width, ysize = tile_height, src = source, trg = target)
            os.system(command)

    # Build KML
    xml_header = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{0}</name>
""".format(basename)
    xml_footer = """
  </Document>
</kml>
"""
    xml = ""
    for i in range(i_max):
        for j in range(j_max):
            tile = os.path.join(basedir, "{0}-{1:0>3d}-{2:0>3d}.jpg".format(basename, i, j))
            dataset = gdal.Open(tile) # print dataset.GetMetadata()
            (east, west, north, south) = get_extent(dataset)

            xml += """
  <GroundOverlay>
    <name>{name}</name>
    <description>{desc}</description>
    <drawOrder>30</drawOrder>
    <Icon><href>{file}</href></Icon>
    <LatLonBox>
      <north>{n}</north>
      <south>{s}</south>
      <east>{e}</east>
      <west>{w}</west>
      <rotation>0.0</rotation>
    </LatLonBox>
  </GroundOverlay>
""".format(name = "{0}-{1:0>3d}-{2:0>3d}".format(basename, i, j), desc = "", file = "{0}-{1:0>3d}-{2:0>3d}.jpg".format(basename, i, j), n = north, s = south, e = east, w = west)

    kml = open(os.path.join(basedir, "{0}.kml".format(basename)), 'w')
    kml.write(xml_header)
    kml.write(xml)
    kml.write(xml_footer)
    kml.close()

#    # Build KMZ
#    kmz = zipfile.ZipFile("{0}.kmz".format(basename), 'w')
#    kmz.write(os.path.join(out_folder, t_name), t_name)
#    os.remove(os.path.join(out_folder, t_name))


    return 0

if __name__ == '__main__':
    main()

