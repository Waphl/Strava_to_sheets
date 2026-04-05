import os, json, requests
from flask import Flask, request, jsonify
from datetime import timedelta
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# webhook logic here:

def get_sheet():
    creds_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1

def get_access_token():
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id":     os.environ["STRAVA_CLIENT_ID"],
        "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
        "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
    })
    return resp.json()["access_token"]
    
def fetch_activity(activity_id):
    token = get_access_token()
    resp = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    return resp.json()

def meters_to_miles(m):
    return round(m / 1609.344, 2)

def seconds_to_hms(s):
    return str(timedelta(seconds=int(s)))[2:]

def find_row_by_activity_id(sheet, activity_id):
    col = sheet.col_values(8)  # Activity ID is column 8
    for i, val in enumerate(col):
        if val == str(activity_id):
            return i + 1  # Sheets rows are 1-indexed
    return None

def avg_pace(distance_m, time_s):
    if distance_m == 0:
        return "—"
    secs_per_mile = time_s / meters_to_miles(distance_m)
    mins, secs = divmod(int(secs_per_mile), 60)
    return f"{mins}:{secs:02d}/mi"
    
@app.route("/webhook", methods=["GET", "POST", "HEAD"])
def webhook():
    if request.method == "HEAD":
        return "OK", 200
    if request.method == "GET":
        challenge = request.args.get("hub.challenge")
        token     = request.args.get("hub.verify_token")
        if token == os.environ["STRAVA_VERIFY_TOKEN"]:
            return jsonify({"hub.challenge": challenge})
        return "Forbidden", 403

    data = request.json
    if data.get("object_type") == "activity" and data.get("aspect_type") in ("create", "update"):
        activity = fetch_activity(data["object_id"])

        if activity.get("type") != "Run":
            return "OK", 200

        row = [
            activity.get("start_date_local", "")[:10],
            activity.get("name", ""),
            meters_to_miles(activity.get("distance", 0)),
            seconds_to_hms(activity.get("moving_time", 0)),
            avg_pace(activity.get("distance", 0), activity.get("moving_time", 0)),
            activity.get("description", ""),
            activity.get("perceived_exertion", ""),
            str(data["object_id"]),
        ]

        sheet = get_sheet()
        existing_row = find_row_by_activity_id(sheet, data["object_id"])

        if existing_row:
            sheet.update(f"A{existing_row}:H{existing_row}", [row])
        else:
            sheet.append_row(row)

    return "OK", 200
    return "OK", 200

if __name__ == "__main__":
    app.run()
