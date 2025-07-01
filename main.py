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

        # Attempt to apply estimate, skip if Jira rejects it
        if issue.estimate:
            try:
                estimate_str = format_estimate(issue.estimate)
                fields["timetracking"] = {"originalEstimate": estimate_str}
            except Exception as e:
                print(f"Estimate provided but not applied due to Jira screen settings. error: {e}")

        payload = {"fields": fields}

        response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/3/issue",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )

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
def sse(request: Request):
    def event_stream():
        # Send tool metadata once
        metadata = {
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
                                "estimate": {"type": "number", "description": "Estimated hours (1-2)"}
                            },
                            "required": ["projectKey", "summary", "description"]
                        }
                    }
                ]
            })
        }
        yield f"event: {metadata['event']}\ndata: {metadata['data']}\n\n"

        while True:
            if await_request_data(request):
                break
            time.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

def await_request_data(request: Request):
    return await_request_data

@app.post("/tool/create_jira_ticket")
def handle_create_jira_ticket(input: JiraIssue):
    return create_jira_issues(input)
