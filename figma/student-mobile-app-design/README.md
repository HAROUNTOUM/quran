# Student Mobile App Design Generator

This is a local Figma plugin that creates editable mobile app frames for the student experience in this project.

## What It Creates

- Design tokens page
- Splash / welcome screen
- Student home dashboard
- Memorization progress screen
- Live session screen
- Attendance screen
- Notifications and requests screen

The layout is Arabic RTL and follows the app's current product language: green primary color, Quran memorization progress, attendance, sessions, review requests, and student notifications.

## Run It In Figma

1. Open Figma Desktop.
2. Open the file where you want the design created.
3. Go to `Plugins -> Development -> Import plugin from manifest...`.
4. Select:

   `figma/student-mobile-app-design/manifest.json`

5. Run `Plugins -> Development -> Student Mobile App Design Generator`.

Figma will create the frames in the current file. All text, cards, colors, and shapes are editable.

## Notes

- The plugin chooses the best available Arabic-capable font from your Figma environment, preferring `Tajawal`, then `Noto Sans Arabic`, then `IBM Plex Sans Arabic`, then `Arial`, then `Inter`.
- It does not upload anything or require account credentials.
- It uses generated shapes only, so there are no external image dependencies.
