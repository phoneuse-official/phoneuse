# Demo videos

This page has the scripts for the demo videos in the [README](../README.md), a checklist for recording them,
and the steps for adding a finished video.

Every demo only looks things up or reads the screen. None of them sends, buys, deletes or changes anything.

> **Status:** none of these prompts has been tried on a physical iPhone for this launch yet.
> Try each one before recording, and update the **Status** column below.

## The demos

| # | Demo | What it shows | Length | Status |
| --- | --- | --- | --- | --- |
| Hero | Overview (use demo 3) | Prompt in, phone moves, answer out | 20–30 s | Not tried yet |
| 1 | [Describe the screen](#1-describe-the-screen) | Reading the screen | 15–20 s | Not tried yet |
| 2 | [Do a calculation](#2-do-a-calculation) | Tapping buttons in an app | 15–25 s | Not tried yet |
| 3 | [Search the web](#3-search-the-web) | Typing, tapping and reading | 30–45 s | Not tried yet |
| 4 | [Look up a place](#4-look-up-a-place) | Searching inside an app | 20–30 s | Not tried yet |
| 5 | [Browse the App Store](#5-browse-the-app-store) | Reading a list, and not installing | 20–30 s | Not tried yet |
| 6 | [Read the world clock](#6-read-the-world-clock) | Moving between tabs in an app | 15–25 s | Not tried yet |
| 7 | [Stop a task halfway](#7-stop-a-task-halfway) | The **Stop task** button | 15–25 s | Not tried yet |
| 8 | [Drive the phone from your AI agent](#8-drive-the-phone-from-your-ai-agent-mcp) | MCP | 30–45 s | Not tried yet |

## Before you record: checklist

### The phone

- [ ] Use a **test iPhone with no personal data**: no personal Apple Account name, contacts, photos, messages, email or saved passwords.
- [ ] Turn on **Do Not Disturb** on the iPhone and the Mac, so no notifications appear.
- [ ] Give the phone a plain name such as "Demo iPhone". The name shows in the phone menu on the PhoneUse page.
- [ ] For the Maps demo, turn off Location Services for Maps, or only record somewhere you are happy to show. Maps shows where the phone is.

### The Mac

- [ ] Record **only the browser window**, not the whole screen.
- [ ] Close other tabs and windows, and hide bookmarks.
- [ ] Do not show Terminal, Xcode's device list, the `platform/.state` folder or the API docs page. They can show device IDs or the API key.
- [ ] Start recording **after** the PhoneUse page has loaded. The address the launcher opens briefly holds the key; the page removes it right away.
- [ ] For the MCP demo, hide or blur the tool results in your MCP client. They include the phone's device ID.

### After recording

- [ ] **Watch every frame** before uploading, and pause on fast parts. Look for device IDs (serial number, UDID, IMEI), notifications, contacts, names, email addresses, phone numbers, locations and the API key.
- [ ] Trim the clip to the length in the table.
- [ ] Save it as `.mp4` (H.264), which plays in every browser. Keep the file small so it starts quickly.
- [ ] If the task fails or does something unexpected, do not use that take. Record again, or skip the demo and open an issue.

## How to record

**Recommended: record the Mac's screen.** It shows the prompt, the live phone screen and the answer together.

1. Follow the [README quickstart](../README.md#get-the-phone-screen-showing) until the badge next to **Your iPhone** says **Ready**.
2. Press **Shift-Command-5**, choose **Record Selected Portion**, and frame the PhoneUse browser window.
3. Type the prompt, press **Enter**, wait for the answer, then stop the recording.

**Optional close-up:** record the iPhone itself with **Control Center → Screen Recording**.
iPhone recordings include the status bar, so check it for notifications.

## How to add a video

Do not commit video files. `scripts/check-public-tree.py` fails on `.mp4`, `.jpg` and `.jpeg` files,
on any binary file and on any file over 2 MB. The videos live in PhoneUse's Cloudflare R2 storage instead,
and the README links to them. Clicking a link plays the whole video in the browser.

1. Upload the `.mp4` to the public R2 bucket. Use clear file names, such as `demo-3-search-the-web.mp4`.
   Serve the bucket from your own domain: Cloudflare says the default `r2.dev` link is rate-limited and meant only for testing.
2. Also upload a still picture from the video (a `.png` or `.jpg` frame) with the same name, such as `demo-3-search-the-web.png`.
   The README shows this picture, and clicking it opens the video.
3. In `README.md`, find the matching comment, for example `<!-- VIDEO demo-3 ... -->`.
   Replace the `_Video coming soon._` line under it with the picture and a text link:

   ```markdown
   [![Watch: Search the web](https://YOUR-R2-DOMAIN/demo-3-search-the-web.png)](https://YOUR-R2-DOMAIN/demo-3-search-the-web.mp4)

   [▶ Watch the video (40 s)](https://YOUR-R2-DOMAIN/demo-3-search-the-web.mp4)
   ```

4. Do the same for the hero clip in the `<!-- HERO VIDEO -->` slot at the top of the README.
5. Open each link in a private browser window. It must play without signing in.
   If the browser downloads the file instead of playing it, set the file's content type to `video/mp4` in R2.
6. Mark the demo as **Recorded** in the table above.

GitHub does not play videos from other sites inside the README. Its pages only play videos stored on GitHub,
so an R2 video always opens on its own page.

**Every upload is public.** Anyone with the link can watch it, so check the video before you upload it.

## Demo scripts

### 1. Describe the screen

- **Before you start:** open Safari on the phone to an empty start page.
- **Prompt:**
  > Open Safari and describe the current screen. Do not submit anything.
- **Viewers should see:** Safari in front and a short, accurate description of the screen in the chat.

### 2. Do a calculation

- **Before you start:** close Calculator.
- **Prompt:**
  > Open Calculator and work out 128 × 46. Tell me the answer.
- **Viewers should see:** the keys being tapped on the live screen, and the answer 5,888.
- **Use another take if:** it taps the wrong keys or the answer is wrong.

### 3. Search the web

This is also the **hero clip**: it shows typing, tapping and reading in one task.

- **Before you start:** open Safari to an empty start page.
- **Prompt:**
  > Open Safari, search for "easy hikes near San Francisco", and summarize the top three results. Do not sign in or fill in any forms.
- **Viewers should see:** the search typed into Safari, results loading, and a three-item summary in the chat.
- **Use another take if:** a sign-in or cookie prompt appears. Do not accept anything on the phone.

### 4. Look up a place

- **Before you start:** see the Maps item in the checklist.
- **Prompt:**
  > Open Maps, search for "Golden Gate Bridge", and tell me its address. Do not start directions.
- **Viewers should see:** Maps searching, the bridge on the map, and the address in the chat.
- **Use another take if:** it starts directions.

### 5. Browse the App Store

- **Before you start:** the App Store shows the signed-in account's picture. Use a test Apple Account.
- **Prompt:**
  > Open the App Store, search for "habit tracker", and list the top three apps with their ratings. Do not tap Get or install anything.
- **Viewers should see:** the search results and three app names with ratings in the chat.
- **Stop at once if:** it moves toward **Get**. Click **Stop task** and do not use that take.

### 6. Read the world clock

- **Before you start:** by hand, add three or four cities to World Clock, such as London, Tokyo and New York.
- **Prompt:**
  > Open Clock, go to World Clock, and tell me which cities are listed and the time in each. Do not add or delete anything.
- **Viewers should see:** the World Clock tab opening, and each city with its time in the chat.

### 7. Stop a task halfway

- **Before you start:** open Safari to an empty start page.
- **Prompt:**
  > Open Safari, search for "iPhone tips", and read me the title of every result on the first page.
- **During the task:** after two or three steps, click the **Stop task** button next to the message box.
- **Viewers should see:** the phone stop moving and the chat show the task as stopped.
  Steps the phone already took are not undone, so say that in the caption.

### 8. Drive the phone from your AI agent (MCP)

- **Before you start:** connect your MCP client to `platform/start-mcp.sh` as described in [INTEGRATIONS.md](INTEGRATIONS.md).
  Put the client window and the PhoneUse page side by side so viewers can see the phone respond.
- **Prompt (in your MCP client):**
  > List my phones, take a screenshot of the first one, and tell me what is on the screen.
- **Viewers should see:** the agent find the phone, take a screenshot, and describe it.
- **Before publishing:** blur or hide the tool results. They include the phone's device ID.
