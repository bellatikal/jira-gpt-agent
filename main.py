from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Union
import requests
import os

app = FastAPI()

class JiraIssue(BaseModel):
    projectKey: str
    summary: str
    description: str
    issueType: str = "Task"
    estimate: float = None  # in hours, optional

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

        # Add estimate as originalEstimate in minutes if provided
        if issue.estimate:
            fields["timetracking"] = {
                "originalEstimate": f"{round(issue.estimate * 60)}m"
            }

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
