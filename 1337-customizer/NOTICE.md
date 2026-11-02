# NOTICE

1337-Customizer is an independent project. Its own source is MIT-licensed.

## Bundled video engine

`engine/bin/mpvpaper` and `engine/mpvpaper-src.tar.gz` come from
[mpvpaper](https://github.com/GhostNaN/mpvpaper), licensed under GPL-3.0.
The full license text is in `engine/LICENSE-mpvpaper`. The source archive is
included so the binary can be rebuilt locally with:

```bash
engine/build-mpvpaper.sh --force
```

mpvpaper is a separate executable invoked at runtime; 1337-Customizer does not
link it into the application.

## Inspiration

The feature direction is inspired by Wallpaper Studio Plus by Adil Asselman
(yuxev) and by the broader Linux desktop-customisation community. No code from
that project is included; 1337-Customizer is a from-scratch GTK 4 application.
