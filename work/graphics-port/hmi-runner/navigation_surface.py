"""OSM navigation video surface for the NBT viewer; not BMW's original map engine."""
import concurrent.futures
import datetime
import io
import json
import math
from pathlib import Path
import threading
import time
import urllib.request
from PIL import Image, ImageDraw, ImageEnhance, ImageFont


def world(lat, lon, zoom):
    lat = max(-85.05112878, min(85.05112878, lat))
    scale = 256 * 2 ** zoom
    return ((lon + 180) / 360 * scale,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * scale)


def distance(a, b):
    lat1, lat2 = map(math.radians, (a[0], b[0]))
    dlat, dlon = lat2-lat1, math.radians(b[1]-a[1])
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


class NavigationSurface:
    def __init__(self, cache_dir=None, width=1280, height=480):
        self.cache = Path(cache_dir or Path(__file__).parent / 'map-cache')
        self.cache.mkdir(parents=True, exist_ok=True)
        self.width, self.height = width, height
        self.origin = (44.4268, 26.1025)
        self.destination = None
        self.position = self.origin
        self.zoom = 15
        self.route = []
        self.steps = []
        self.route_metres = self.route_seconds = 0
        self.progress = 0
        self.message = 'Demo position: Bucharest. Set a destination to route.'
        self._tiles, self._pending, self._failures = {}, set(), {}
        self._lock = threading.RLock()
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix='osm')
        self._closed = False
        self._generation = 0
        self._stamp = 0
        self._last_frame = None
        try:
            self.font = ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf', 18)
            self.title_font = ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf', 28)
            self.small_font = ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf', 14)
        except OSError:
            self.font = self.title_font = self.small_font = ImageFont.load_default()

    @staticmethod
    def coordinate(value):
        if len(value) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
            raise ValueError('Coordinates must be finite latitude/longitude numbers')
        lat, lon = value
        if not -85 <= lat <= 85 or not -180 <= lon <= 180:
            raise ValueError('Coordinates are outside the supported map range')
        return float(lat), float(lon)

    def configure(self, origin=None, destination=None, zoom=None):
        origin = self.coordinate(origin) if origin is not None else self.origin
        destination = self.coordinate(destination) if destination is not None else None
        if zoom is not None and (type(zoom) is not int or not 3 <= zoom <= 18):
            raise ValueError('Zoom must be an integer from 3 to 18')
        with self._lock:
            self.origin = self.position = origin
            self.destination = destination
            self.zoom = self.zoom if zoom is None else zoom
            self.route, self.steps, self.progress = [], [], 0
            self._generation += 1
            generation = self._generation
            if destination is not None:
                self.message = 'Calculating a driving route…'
                self._pool.submit(self._route, origin, destination, generation)
        return self.status()

    def _request(self, url):
        return urllib.request.Request(url, headers={'User-Agent': 'BMW-NBT-Emulator/1.0 (local experimental navigation)'})

    def _route(self, origin, destination, generation):
        coordinates = f'{origin[1]},{origin[0]};{destination[1]},{destination[0]}'
        url = 'https://router.project-osrm.org/route/v1/driving/' + coordinates + '?overview=full&geometries=geojson&steps=true'
        try:
            with urllib.request.urlopen(self._request(url), timeout=20) as response:
                data = json.loads(response.read(4 * 1024 * 1024))
            if data.get('code') != 'Ok' or not data.get('routes'):
                raise ValueError('No driving route was found')
            route = data['routes'][0]
            points = [(float(lat), float(lon)) for lon, lat in route['geometry']['coordinates']]
            steps = [step for leg in route['legs'] for step in leg.get('steps', [])]
            with self._lock:
                if generation != self._generation or self._closed:
                    return
                self.route, self.steps = points, steps
                self.route_metres, self.route_seconds = route['distance'], route['duration']
                self.message = 'Route ready · simulated position'
        except (OSError, ValueError, KeyError, TypeError) as error:
            with self._lock:
                if generation == self._generation:
                    self.message = 'Routing unavailable: ' + str(error)[:100]

    def _load_tile(self, key):
        z, x, y = key
        path = self.cache / f'{z}-{x}-{y}.png'
        try:
            if not path.exists() or time.time() - path.stat().st_mtime > 7 * 86400:
                with urllib.request.urlopen(self._request(f'https://tile.openstreetmap.org/{z}/{x}/{y}.png'), timeout=10) as response:
                    data = response.read(1024 * 1024)
                image = Image.open(io.BytesIO(data)).convert('RGB')
                if image.size != (256, 256):
                    raise ValueError('Unexpected map tile dimensions')
                temporary = path.with_suffix('.tmp')
                temporary.write_bytes(data)
                temporary.replace(path)
            else:
                with Image.open(path) as source:
                    image = source.convert('RGB')
            with self._lock:
                # Keep the road labels crisp while softening the bright web-map
                # palette towards the muted green/cream OEM daytime display.
                image = ImageEnhance.Color(image).enhance(.72)
                self._tiles[key] = Image.blend(image, Image.new('RGB', image.size, '#d5dfc6'), .12)
                if len(self._tiles) > 96:
                    self._tiles.pop(next(iter(self._tiles)))
        except (OSError, ValueError):
            with self._lock:
                self._failures[key] = time.monotonic()
        finally:
            with self._lock:
                self._pending.discard(key)

    def status(self):
        with self._lock:
            return {'source': 'OpenStreetMap / OSRM', 'position': self.position, 'demo_position': True,
                    'destination': self.destination, 'route_metres': self.route_metres,
                    'route_seconds': self.route_seconds, 'message': self.message, 'zoom': self.zoom,
                    'original_bmw_map_engine': False}

    def action(self, name):
        with self._lock:
            if name in ('up', 'down'):
                self.zoom = min(18, max(3, self.zoom + (1 if name == 'up' else -1)))
            elif name == 'select':
                self.position = self.origin
            elif name.startswith('tilt_'):
                lat, lon = self.position
                amount = 60 / (2 ** self.zoom)
                self.position = (max(-85, min(85, lat + (amount if name == 'tilt_up' else -amount if name == 'tilt_down' else 0))),
                                 max(-180, min(180, lon + (amount if name == 'tilt_right' else -amount if name == 'tilt_left' else 0))))

    def advance(self, seconds, speed_kph):
        if not math.isfinite(seconds) or not math.isfinite(speed_kph) or seconds < 0 or not 0 <= speed_kph <= 300:
            raise ValueError('Invalid route simulation interval or speed')
        with self._lock:
            if len(self.route) < 2:
                return
            self.progress = min(self.route_metres, self.progress + seconds * speed_kph / 3.6)
            remaining = self.progress
            for a, b in zip(self.route, self.route[1:]):
                length = distance(a, b)
                if remaining <= length:
                    fraction = remaining / length if length else 0
                    self.position = (a[0] + (b[0]-a[0])*fraction, a[1] + (b[1]-a[1])*fraction)
                    break
                remaining -= length
            else:
                self.position = self.route[-1]

    def frame(self):
        # Only displayed viewport tiles are requested. No offline/bulk prefetch.
        with self._lock:
            if self._closed:
                return None
            if self._last_frame and time.monotonic() - self._stamp < .25:
                return self._last_frame
            map_width = self.width
            cx, cy = world(*self.position, self.zoom)
            left, top = cx-map_width/2, cy-self.height/2
            image = Image.new('RGB', (self.width, self.height), '#101820')
            for tx in range(math.floor(left/256), math.floor((left+map_width)/256)+1):
                for ty in range(math.floor(top/256), math.floor((top+self.height)/256)+1):
                    if not 0 <= ty < 2**self.zoom:
                        continue
                    key = (self.zoom, tx % 2**self.zoom, ty)
                    tile = self._tiles.get(key)
                    if tile:
                        image.paste(tile, (round(tx*256-left), round(ty*256-top)))
                    elif key not in self._pending and time.monotonic()-self._failures.get(key, -100) > 30:
                        self._pending.add(key)
                        self._pool.submit(self._load_tile, key)
            draw = ImageDraw.Draw(image)
            if self.route:
                points = [(world(lat, lon, self.zoom)[0]-left, world(lat, lon, self.zoom)[1]-top) for lat, lon in self.route]
                draw.line(points, fill='#f4f0dc', width=11, joint='curve')
                draw.line(points, fill='#397ba4', width=6, joint='curve')
            self._draw_oem_controls(draw)
            px, py = map_width/2, self.height/2
            # Original-style direction marker, outlined for visibility on roads.
            draw.ellipse((px-17, py-17, px+17, py+17), fill='#dde8e5', outline='#324d55', width=2)
            draw.polygon([(px,py-15),(px-10,py+12),(px,py+7),(px+10,py+12)], fill='#b93627', outline='#fff9e9', width=2)
            output = io.BytesIO()
            image.save(output, format='PPM')
            self._last_frame, self._stamp = output.getvalue(), time.monotonic()
            return self._last_frame

    def _draw_oem_controls(self, draw):
        ink, edge, panel = '#ecebdc', '#70817b', '#273d3c'
        # Narrow icon strip leaves the complete map visible, as on OEM NBT.
        draw.rectangle((0,0,42,self.height), fill=panel)
        draw.line((42,0,42,self.height), fill=edge)
        for y in range(8,257,41):
            draw.line((4,y+34,37,y+34), fill='#61716a')
        # Destination flag, guidance arrow, sound, search, map layers, settings.
        draw.line((12,14,12,35), fill=ink, width=2)
        draw.polygon([(13,14),(31,17),(25,23),(13,21)], outline=ink)
        draw.line([(11,68),(22,53),(32,68)], fill=ink, width=3)
        draw.line((22,55,22,76), fill=ink, width=3)
        draw.polygon([(11,99),(17,99),(25,92),(25,114),(17,107),(11,107)], outline=ink)
        draw.arc((18,94,34,113),-65,65,fill=ink,width=2)
        draw.ellipse((11,134,27,150),outline=ink,width=2)
        draw.line((26,149,33,157),fill=ink,width=3)
        for shift in (0,6):
            draw.line([(9,184+shift),(21,178+shift),(34,184+shift),(21,190+shift),(9,184+shift)],fill=ink,width=2)
        draw.ellipse((11,218,32,239),outline=ink,width=2)
        draw.text((18,219),'i',font=self.small_font,fill=ink)
        # Clock and north indicator occupy small translucent-looking plaques.
        clock=datetime.datetime.now().strftime('%H:%M')
        draw.rectangle((self.width-102,8,self.width-9,39),fill=panel,outline=edge)
        draw.text((self.width-79,11),clock,font=self.font,fill=ink)
        draw.ellipse((self.width-53,51,self.width-13,91),fill=panel,outline=edge,width=1)
        draw.text((self.width-39,52),'N',font=self.small_font,fill=ink)
        draw.polygon([(self.width-33,69),(self.width-39,83),(self.width-33,80),(self.width-27,83)],fill='#ce4b37')
        # A true metric scale calculated from latitude and Web Mercator zoom.
        metres_per_pixel=156543.03392*math.cos(math.radians(self.position[0]))/(2**self.zoom)
        target=130*metres_per_pixel
        magnitude=10**math.floor(math.log10(max(1,target)))
        scale=max(value*magnitude for value in (1,2,5,10) if value*magnitude<=target)
        length=max(15,round(scale/metres_per_pixel))
        y=self.height-26
        draw.rectangle((50,y-18,66+length,self.height-6),fill=panel)
        label=f'{scale/1000:g} km' if scale>=1000 else f'{scale:g} m'
        draw.text((57,y-18),label,font=self.small_font,fill=ink)
        draw.line([(57,y),(57,y+5),(57+length,y+5),(57+length,y)],fill=ink,width=2)
        attribution='© OpenStreetMap contributors'
        box=draw.textbbox((0,0),attribution,font=self.small_font)
        x=self.width-(box[2]-box[0])-17
        draw.rectangle((x-6,self.height-24,self.width,self.height),fill=panel)
        draw.text((x,self.height-23),attribution,font=self.small_font,fill=ink)
        if self.route:
            text=f'{max(0,self.route_metres-self.progress)/1000:.1f} km'
            draw.rectangle((self.width-151,103,self.width-9,136),fill=panel,outline=edge)
            draw.text((self.width-133,107),text,font=self.font,fill=ink)

    def close(self):
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)
