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
from osgeo import osr

import os
import argparse
from tempfile import mkdtemp
from zipfile import ZipFile

from math import ceil


QUALITY = 75
MAX_WIDTH  = 1024
MAX_HEIGHT = 1024
MAX_TILE_NUMBER = 100
SRS_GPS_EPSG = 4326


def get_extent(raster):
    (cols, rows) = (raster.RasterXSize, raster.RasterYSize)

    geotransform = raster.GetGeoTransform()
    (originX,    originY)     = (geotransform[0], geotransform[3])
    (pixelWidth, pixelHeight) = (geotransform[1], geotransform[5])

    xMax = originX + cols*pixelWidth
    xMin = originX
    yMax = originY
    yMin = originY - rows*pixelHeight

    return (xMax, xMin, yMax, yMin)


class Tile(object):

    def __init__(self, i, j, width, height, parent):
        self.parent = parent
        self.i = i
        self.j = j
        self.name = "{0:0>2d}{1:0>2d}".format(i, j)
        self.width = width
        self.height = height
        self.file = None
        self.extent = None
        self.file_aux = None
        self.file_world = None

    def get_file(self):
        return self.file

    def get_file_aux(self):
        return self.file_aux

    def get_file_world(self):
        return self.file_world

    def generate(self, dir, quality):
        self.file       = os.path.join(dir, "{0}.jpg".format(self.name))
        self.file_aux   = os.path.join(dir, "{0}.aux.xml".format(self.file))
        self.file_world = os.path.join(dir, "{0}.wld".format(self.name))

        command = """gdal_translate -of JPEG -co WORLDFILE=YES -co QUALITY={quality} -expand gray \
-srcwin {xoff:.0f} {yoff:.0f} {xsize:.0f} {ysize:.0f} \
{src} {trg}""".format(xoff = self.j*self.width, yoff = self.i*self.height,
xsize = self.width, ysize = self.height,
src = self.parent, trg = self.file,
quality = quality)

        os.system(command) # TODO: Achieve this with pure Python

        dataset = gdal.Open(self.file)
        self.extent = get_extent(dataset)

        return 0

    def to_kml(self):
        (east, west, north, south) = self.extent
        xml = """
    <GroundOverlay>
      <name>{name}</name><description>{desc}</description>
      <drawOrder>30</drawOrder>
      <Icon><href>{file}</href></Icon>
      <LatLonBox>
        <north>{n}</north><south>{s}</south>
        <east>{e}</east><west>{w}</west>
        <rotation>0.0</rotation>
      </LatLonBox>
    </GroundOverlay>""".format(name = self.name, desc = "",
        file = "{0}.jpg".format(self.name), n = north, s = south, e = east, w = west)

        return xml


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("src", help="Input")
    parser.add_argument("trg", help="Output")
    args = parser.parse_args()

    src = args.src
    trg = args.trg

    name     = os.path.basename(trg)
    basename = os.path.splitext(name)[0]

    src_srs = None
    trg_srs = osr.SpatialReference()
    trg_srs.ImportFromEPSG(SRS_GPS_EPSG)

    # Create temporary output directory
    workdir = mkdtemp('', "{0}_".format(basename))

    target = None
    if src_srs != trg_srs:
        # Reproject to WGS84
        target = os.path.join(workdir, "{0}.vrt".format(basename))

        command = "gdalwarp -of VRT -t_srs EPSG:4326 {src} {trg}".format(src = src, trg = target)
        os.system(command) # TODO: Achieve this with pure Python
    else:
        target = src


    # Get extent
    dataset = gdal.Open(target)
    (width, height) = (dataset.RasterXSize, dataset.RasterYSize)

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

    tile_count = i_max*j_max
    if tile_count > MAX_TILE_NUMBER:
        print "WARNING: KML can handle 100 tiles max (asking for {0}).".format(tile_count)

    print "Creating {0} tiles ({1}x{2}) of {3}x{4} pixels.".format(i_max*j_max, j_max, i_max, tile_width, tile_height)


    # Build tiles
    # Parallelize this? chriskiehl.com/article/parallelism-in-one-line
    source = os.path.join(workdir, "{0}.vrt".format(basename))
    tiles = []
    for i in range(i_max):
        for j in range(j_max):
            tile = Tile(i, j, tile_width, tile_height, source)
            tile.generate(workdir, QUALITY)

            tiles.append(tile)
    os.remove(source)


    # Build KML
    print "Building KML..."
    xml_header = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document><name>{0}</name>
""".format(basename)
    xml_footer = """
  </Document>
</kml>
"""
    xml_body = '\n'.join([t.to_kml() for t in tiles])

    kml = open(os.path.join(workdir, "doc.kml"), 'w')
    kml.write(xml_header)
    kml.write(xml_body)
    kml.write(xml_footer)
    kml.close()


    # Build KMZ
    print "Building KMZ..."
    kmz = ZipFile(trg, 'w')
    for tile in tiles:
        kmz.write(tile.get_file(), os.path.basename(tile.get_file()))
        os.remove(tile.get_file())

        #kmz.write(tile.get_file_world(), os.path.basename(tile.get_file_world()))
        #kmz.write(tile.get_file_aux(), os.path.basename(tile.get_file_aux()))
        os.remove(tile.get_file_world())
        os.remove(tile.get_file_aux())

    kmz.write(os.path.join(workdir, "doc.kml"), "doc.kml")
    os.remove(os.path.join(workdir, "doc.kml"))
    kmz.close()

    # Delete temporary output directory
    os.rmdir(workdir)

    return 0

if __name__ == '__main__':
    main()

