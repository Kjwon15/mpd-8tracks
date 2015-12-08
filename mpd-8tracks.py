###################################
# Project: mpd8tracks
# Author: Shane Creighton-Young
#
# Usage: 
# python mpd8tracks [url to an 8tracks mix]...
#
# Dependencies:
# - bash shell
# - mpd and mpc
# - an 8tracks developer api key
#
# Recommended:
# - another mpd client to actually manage the music playing
#
# Notes:
# - another song will be added if the playlist is changed at all
# - doesn't queue another playlist automatically; only exits
#
# Contributors:
# omsmith
# xLegoz

import sys
import urllib2
import os
import json
import time
import socket

def normalize(s):
   t = s.encode('ascii', 'ignore')
   return t.translate(None, "'/")

def fix_track_url(url):
   if (url[:5] == 'https'):
      return 'http' + url[5:]
   return url


class Mpd():

   def __init__(self, host=None, port=None, password=None):
      self.host = host or 'localhost'
      self.port = port or 6600
      self.password = password

      self._connect()

   def command(self, commands):
      if not isinstance(commands, str):
         commands = ('command_list_begin\n' +
                     ('\n'.join(commands) + '\n') +
                     'command_list_end\n')

      self._command(commands)

   def _connect(self):
      if hasattr(self, 'sock'):
         self.sock.close()

      self.sock = socket.socket()
      self.sock.connect((self.host, self.port))

      if self.password:
         self.sock.send('password {}\n'.format(self.password))

      self.sock.recv(1024)

   def _command(self, command):
      while 1:
         try:
            self.sock.send(command)
            self.sock.recv(1024)
         except socket.error:
            self._connect()
         else:
            break


# Open config file
config = None
try:
    with open('config.json') as config_text:
        config = json.load(config_text)
except IOError:
    print >> sys.stderr, "WARN: No config.json file"

# Check and process input options, url(s)
mix_urls = []
if (len(sys.argv) == 1):
   print >> sys.stderr, "ERR: Usage: python mpd8tracks [url to an 8tracks mix]..."
   sys.exit(2)
for url in sys.argv[1:]:
   i = url.find("8tracks.com")
   if i != -1:
      mix_urls.append(url[i+11:])

# Open the API developer key
# TODO: Should check that this API key is valid
api_key = None
if (config == None or config['apikey'] == None):
   try:
      api_key = raw_input("Enter API Key: ")
   except KeyboardInterrupt:
      print
      sys.exit(1)
else:
   print "Using API Key from config.json..."
   api_key = config['apikey']

# MPD config
mpd_host = config.get('mpd_host', None)
mpd_port = config.get('mpd_port', None)
mpd_password = config.get('mpd_password', None)
mpd_client = Mpd(mpd_host, mpd_port, mpd_password)

# we're using api version 3
api_version = "3"

def api_call(path, **kwargs):
   query = "https://8tracks.com/%s.jsonp?api_version=%s&api_key=%s" % (path, api_version, api_key)
   for key in kwargs:
      query = "%s&%s=%s" % (query, key, kwargs[key])
   return json.loads(urllib2.urlopen(query).read())

# Set up mpd
mpd_client.command(['clear', 'consume 1'])

# Get the play token
play_token_info = api_call("sets/new")
play_token = play_token_info['play_token']

for mix_url in mix_urls:
   # Get the mix information, extract the mix id
   mix_info = api_call(mix_url)
   mix_id = mix_info['mix']['id']
   mix_name = normalize(mix_info['mix']['name'])
   download = config.get('download', False)

   # Create the playlist directory if we're downloading the music
   if (download):
       os.system("mkdir -p \"playlists/%s\" 1>/dev/null 2>/dev/null" % mix_name)

   # Let the user know which mix is playing
   print "Now playing: \"%s\"" % mix_name

   # Song playing loop
   while True:

      # Get the song info crom 8tracks api
      song_info = api_call("sets/%s/next" % play_token, mix_id=mix_id)

      # If we can't request the next one due to time restrictions, sleep and try again
      if (song_info['status'] == "403 Forbidden"):
        time.sleep(30)
        continue

      # Get relevant information and save it
      track_id = song_info['set']['track']['id']
      artist = normalize(song_info['set']['track']['performer'])
      name = normalize(song_info['set']['track']['name'])
      track_url = song_info['set']['track']['track_file_stream_url']

      # Fix the track URL (https://api.soundcloud/foo links don't work and need
      # to be converted to http://api.soundcloud/foo)
      track_url = fix_track_url(track_url)

      print "Enqueuing: %s - \"%s\"" % (artist, name)

      if (download):
         # Download the song
         print "Downloading: %s - \"%s\"" % (artist, name)
         f = urllib2.urlopen(track_url)
         with open("playlists/%s/%s - %s.mp3" % (mix_name, artist, name),
                  "w+") as song:
            song.write(f.read())

      # Notify 8tracks that the song is being played
      api_call("sets/%s/report" % play_token, mix_id=mix_id, track_id=track_id)

      # Queue the song via mpc
      mpd_client.command([
         'add "{}"'.format(track_url),
         'play',
      ])

      # If we're at the end of the mix finish up
      if song_info['set']['at_end']:
         print "Finished playing %s" % mix_name
         break
