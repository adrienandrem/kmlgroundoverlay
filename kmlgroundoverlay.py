#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 2015-03-05T13:51:15-0300

@author: aandre
"""
import os
import logging

import rasterio

import argparse
from tempfile import mkdtemp
from zipfile import ZipFile

from math import ceil


QUALITY = 75
MAX_WIDTH  = 1024
MAX_HEIGHT = 1024
MAX_TILE_NUMBER = 100
TRG_SRS = rasterio.crs.CRS.from_epsg(4326)
#COMMAND_TILE = """gdal_translate -of JPEG -co WORLDFILE=YES -co QUALITY={quality} -expand gray -srcwin {xoff:.0f} {yoff:.0f} {xsize:.0f} {ysize:.0f} {src} {trg}"""
COMMAND_TILE = """gdal_translate -of JPEG -co WORLDFILE=YES -co QUALITY={quality}              -srcwin {xoff:.0f} {yoff:.0f} {xsize:.0f} {ysize:.0f} {src} {trg}"""
XML_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document><name>{0}</name>
"""
XML_TILE = """
    <GroundOverlay>
      <name>{name}</name><description>{desc}</description>
      <drawOrder>30</drawOrder>
      <Icon><href>{file}</href></Icon>
      <LatLonBox>
        <north>{n}</north><south>{s}</south>
        <east>{e}</east><west>{w}</west>
        <rotation>0.0</rotation>
      </LatLonBox>
    </GroundOverlay>"""
XML_FOOTER = """
  </Document>
</kml>
"""


logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))


def get_extent(raster):
    """Raster bounding box"""

    xMin, yMin, xMax, yMax = raster.bounds  # left, bottom, right, top

    return xMax, xMin, yMax, yMin


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
        """Generate raster file"""
        self.file       = os.path.join(dir, "{0}.jpg".format(self.name))
        self.file_aux   = os.path.join(dir, "{0}.aux.xml".format(self.file))
        self.file_world = os.path.join(dir, "{0}.wld".format(self.name))

        command = COMMAND_TILE.format(xoff = self.j*self.width, yoff = self.i*self.height,
xsize = self.width, ysize = self.height,
src = self.parent, trg = self.file,
quality = quality)

        os.system(command) # TODO: Achieve this with pure Python

        with rasterio.open(self.file) as dataset:
            self.extent = get_extent(dataset)

        return 0

    def to_kml(self):
        east, west, north, south = self.extent
        xml = XML_TILE.format(name = self.name, desc = "",
        file = "{0}.jpg".format(self.name), n = north, s = south, e = east, w = west)

        return xml


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("src", help="Input raster file (ex.: map.tif)")
    parser.add_argument("trg", help="Output file (ex.: map.kml)")
    args = parser.parse_args()

    src = args.src
    trg = args.trg

    name     = os.path.basename(trg)
    basename = os.path.splitext(name)[0]

    src_srs = None

    # Create temporary output directory
    workdir = mkdtemp('', "{0}_".format(basename))

    target = None
    if src_srs != TRG_SRS:
        # Reproject to WGS84
        target = os.path.join(workdir, "{0}.vrt".format(basename))

        command = "gdalwarp -of VRT -t_srs EPSG:4326 {src} {trg}".format(src = src, trg = target)
        os.system(command)  # TODO: Achieve this with pure Python
    else:
        target = src


    # Get extent
    with rasterio.open(target) as dataset:
        width, height = dataset.width, dataset.height

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
            logging.warn("KML can handle a maximum of 100 tiles (asking for %s).", tile_count)

        logging.info("Creating %s tiles (%sx%s) of %sx%s pixels.", i_max*j_max, j_max, i_max, tile_width, tile_height)


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
        logging.info("Building KML...")
        xml_header = XML_HEADER.format(basename)
        xml_footer = XML_FOOTER
        xml_body = '\n'.join([t.to_kml() for t in tiles])

        kml = open(os.path.join(workdir, "doc.kml"), 'w')
        kml.write(xml_header)
        kml.write(xml_body)
        kml.write(xml_footer)
        kml.close()


        # Build KMZ
        logging.info("Building KMZ...")
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

    return 1

if __name__ == '__main__':
    main()
