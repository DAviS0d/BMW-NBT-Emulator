import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from navigation_surface import NavigationSurface, world, distance
from PIL import Image


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.surface = NavigationSurface(cache_dir=self.directory.name)
        self.addCleanup(self.surface.close)

    def test_coordinates_and_mercator(self):
        self.assertEqual(world(0,0,0),(128,128))
        self.assertAlmostEqual(distance((0,0),(0,1)),111194.9,delta=1)
        for value in ((float('nan'),0),(100,0),(0,181),(True,0)):
            with self.assertRaises(ValueError):
                self.surface.coordinate(value)

    def test_visible_map_frame_is_real_ppm_and_bounded_tile_requests(self):
        with patch.object(self.surface._pool,'submit') as requests:
            payload = self.surface.frame()
        with Image.open(io.BytesIO(payload)) as image:
            self.assertEqual(image.size,(1280,480))
        # Full-screen viewport plus the partially visible edge tiles only.
        limit=(math.ceil(self.surface.width/256)+1)*(math.ceil(self.surface.height/256)+1)
        self.assertLessEqual(requests.call_count,limit)
        self.assertTrue(self.surface.status()['demo_position'])
        self.assertFalse(self.surface.status()['original_bmw_map_engine'])

    def test_real_route_schema_is_converted_and_followed(self):
        response = {'code':'Ok','routes':[{'distance':1112,'duration':100,
                    'geometry':{'coordinates':[[26,44],[26.01,44]]},'legs':[{'steps':[]}]}]}
        class Reply(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*args): self.close()
        with patch('navigation_surface.urllib.request.urlopen',return_value=Reply(json.dumps(response).encode())):
            self.surface._route((44,26),(44,26.01),0)
        self.surface.advance(5,36)
        self.assertGreater(self.surface.position[1],26)
        self.assertLess(self.surface.position[1],26.01)
        self.assertEqual(self.surface.status()['route_metres'],1112)

    def test_zoom_is_bounded_and_invalid_input_does_not_change_origin(self):
        for _ in range(30): self.surface.action('up')
        self.assertEqual(self.surface.zoom,18)
        before = self.surface.origin
        with self.assertRaises(ValueError): self.surface.configure(origin=(99,0))
        self.assertEqual(self.surface.origin,before)


if __name__ == '__main__': unittest.main()
