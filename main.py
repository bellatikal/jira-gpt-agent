from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Union
import requests
import os
import time
import json
from fastapi.responses import StreamingResponse

app = FastAPI()

class JiraIssue(BaseModel):
    projectKey: str
    summary: str
    description: str
    issueType: str = "Task"
    estimate: float = None  # in hours, optional
    assignee: str = None  # display name
    epic: str = None      # must be an epic issue key

def format_estimate(hours: float) -> str:
    total_minutes = int(hours * 60)
    weeks = total_minutes // (5 * 8 * 60)
    days = (total_minutes % (5 * 8 * 60)) // (8 * 60)
    remaining_minutes = total_minutes % (8 * 60)
    h = remaining_minutes // 60
    m = remaining_minutes % 60

    parts = []
    if weeks > 0:
        parts.append(f"{weeks}w")
    if days > 0:
        parts.append(f"{days}d")
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")

    return " ".join(parts) if parts else "1h"

@app.post("/create-jira-issue")
def create_jira_issues(input: Union[JiraIssue, List[JiraIssue]]):
    JIRA_EMAIL = os.getenv("JIRA_EMAIL")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
    JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")

    if not (JIRA_EMAIL and JIRA_API_TOKEN and JIRA_BASE_URL):
        raise HTTPException(status_code=500, detail="Missing Jira credentials")

    if isinstance(input, JiraIssue):
        input = [input]  # Normalize to list

    results = []
    for issue in input:
        print("Received issue input from GPT:", issue.dict())

        fields = {
            "project": {"key": issue.projectKey},
            "summary": issue.summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": issue.description}
                        ]
                    }
                ]
            },
            "issuetype": {"name": issue.issueType},
        }

        # Estimate
        if issue.estimate:
            try:
                estimate_str = format_estimate(issue.estimate)
                fields["timetracking"] = {"originalEstimate": estimate_str}
            except Exception as e:
                print(f"Estimate not applied: {e}")

        # Assignee
        if issue.assignee:
            user_resp = requests.get(
                f"{JIRA_BASE_URL}/rest/api/3/user/search",
                params={"query": issue.assignee},
                headers={"Accept": "application/json"},
                auth=(JIRA_EMAIL, JIRA_API_TOKEN)
            )
            if user_resp.status_code == 200 and user_resp.json():
                account_id = user_resp.json()[0]["accountId"]
                fields["assignee"] = {"accountId": account_id}
            else:
                print(f"Warning: Assignee '{issue.assignee}' not found or ambiguous.")

        # Epic Link for team-managed project: use 'parent' key
        if issue.epic:
            fields["parent"] = {"key": issue.epic}

        payload = {"fields": fields}

        print("Payload being sent to Jira:")
        print(json.dumps(payload, indent=2))

        response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/3/issue",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )

        print("Jira response status:", response.status_code)
        print("Response body:", response.text)

        if response.status_code >= 400:
            results.append({"error": response.text})
        else:
            data = response.json()
            results.append({
                "issueKey": data.get("key"),
                "issueUrl": f"{JIRA_BASE_URL}/browse/{data.get('key')}"
            })

    return results

@app.get("/sse")
def sse():
    def event_stream():
        tool_metadata = {
            "event": "tool_metadata",
            "data": json.dumps({
                "tools": [
                    {
                        "name": "create_jira_ticket",
                        "description": "Create a Jira ticket in a specific project.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "projectKey": {"type": "string", "description": "The Jira project key"},
                                "summary": {"type": "string", "description": "The ticket title"},
                                "description": {"type": "string", "description": "Details of the task"},
                                "issueType": {"type": "string", "description": "Task type", "default": "Task"},
                                "estimate": {"type": "number", "description": "Estimated hours (1–2)"},
                                "epic": {"type": "string", "description": "Epic issue key (e.g. AAD-15)"},
                                "assignee": {"type": "string", "description": "Display name of the user to assign the ticket to"}
                            },
                            "required": ["projectKey", "summary", "description"]
                        }
                    }
                ]
            })
        }
        print("Tool metadata JSON:", json.dumps(tool_metadata, indent=2))
        yield f"event: {tool_metadata['event']}\ndata: {tool_metadata['data']}\n\n"

        while True:
            time.sleep(15)
            yield f"event: heartbeat\ndata: keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/tool/create_jira_ticket")
async def handle_create_jira_ticket(input: JiraIssue, request: Request):
    data = await request.json()
    print("🔥 Raw incoming GPT tool call:", json.dumps(data, indent=2))
    return create_jira_issues(input)
