
#  PatientTurtle, A Client/Server App for Raspberry Pi Slow-Motion Videos

This purpose of this software is to create a simple client/server application that makes it easier to capture and download data from a Raspberry Pi.  The Raspberry Pi memory is easily exaughsted, and the post-processing steps are much faster if they are done off of the Raspberry Pi.  This application allows one to remotely request a capture, then download all the data to your desktop and post-process the video there.  All the images frames and some metadata (such as the exact capture command used, and final memory usage) are collected into a single .tar file that is sent back to the client for easy processing.

## Documentation/Installation

For information on how to get started recording high speed videos on Raspberry Pi, see this blog post:

[A Guide to Recording 660FPS Video On A $6 Raspberry Pi Camera](https://blog.robertelder.org/recording-660-fps-on-raspberry-pi-camera/)

Note that the example scripts in this repo have a lot of hard-coded paths.  This is an early prototype and not well tested!

## Example Usage

Once you have dcraw and raspiraw downloaded and built, you can launch the server on the Raspberry Pi:

```
python3 slomo_server.py
```

Then, on your desktop client, edit the file 'slomo_client.py' to use the IP address your Raspberry Pi.  Now you can do:

```
python3 slomo_client.py
```

Now, all the video capture data should be stored in a tar file in the current directory.

##  Post-Processing Videos

Now you can do post-processing on the contents of the tar to obtain the final video.  These steps assume that you have the dcraw repo at ~/dcraw and the compiled executable located at ~/dcraw/dcraw.  Here is an example of processing one video:

```
mkdir /dev/shm/slomo
cd /dev/shm/slomo
/capture-location/2019-08-19_14-44-36.692878.tar ./
tar -xvf 2019-08-19_14-44-36.692878.tar
./process-video.sh
 The processed video is now located at output.mp4
```

The 'process-video.sh' may need to be edited if you have a different version of ffmpeg installed.

## TODOs:

-  Support real-time video feed to make it easier to know what the camera currently sees.
-  Support more message types to get more visibility into what is happening on the Pi.
-  More checking for error conditions instead of always assuming success.
-  Review internals of raspiraw and see if there might be a way to do continuous recording.
