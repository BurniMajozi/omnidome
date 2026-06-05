"""FNO Browser Automation Engine.

Provides the core automation capabilities:
  - Screen recording (start/stop/annotation)
  - Mouse tracking (clicks, coordinates, hover)
  - Screenshot capture (full page + element)
  - Process analysis (step recording + playback)
  - UI path extraction (CSS selectors, XPath)

In production, this wraps Puppeteer/Playwright via a subprocess or
container. For now, it provides the data model and job orchestration.
"""

import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class MouseAction:
    """A single mouse action during automation."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    action: str = "click"  # click, double_click, right_click, hover, drag, scroll
    x: int = 0
    y: int = 0
    button: str = "left"
    scroll_delta: int = 0
    target_selector: Optional[str] = None
    target_text: Optional[str] = None
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None


@dataclass
class ScreenRecording:
    """Screen recording metadata for an automation job."""
    job_id: uuid.UUID = field(default_factory=uuid.uuid4)
    started_at: datetime = field(default_factory=datetime.utcnow)
    stopped_at: Optional[datetime] = None
    file_path: Optional[str] = None
    duration_seconds: int = 0
    resolution: str = "1920x1080"
    fps: int = 15
    mouse_actions: list = field(default_factory=list)
    annotations: list = field(default_factory=list)

    def add_mouse_action(self, action: MouseAction):
        self.mouse_actions.append(action)

    def stop(self):
        self.stopped_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = int((self.stopped_at - self.started_at).total_seconds())


@dataclass
class UIElement:
    """Extracted UI element from FNO portal."""
    selector: str = ""
    xpath: str = ""
    tag: str = ""
    text: str = ""
    attributes: dict = field(default_factory=dict)
    bounding_box: dict = field(default_factory=dict)  # x, y, width, height
    is_visible: bool = True
    is_interactable: bool = True
    screenshot_path: Optional[str] = None

    @classmethod
    def from_playwright(cls, element_data: dict) -> "UIElement":
        return cls(
            selector=element_data.get("selector", ""),
            xpath=element_data.get("xpath", ""),
            tag=element_data.get("tag", ""),
            text=element_data.get("text", ""),
            attributes=element_data.get("attributes", {}),
            bounding_box=element_data.get("bounding_box", {}),
        )


@dataclass
class ProcessAnalysis:
    """Analysis of a recorded automation process.
    
    Used to understand the UI path, extract selectors,
    and create reusable templates.
    """
    job_id: uuid.UUID = field(default_factory=uuid.uuid4)
    fno_portal: str = ""
    action_type: str = ""
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    total_duration_seconds: int = 0

    # Extracted patterns
    login_url: Optional[str] = None
    selectors_used: dict = field(default_factory=dict)
    page_transitions: list = field(default_factory=list)
    form_fields: list = field(default_factory=list)
    error_patterns: list = field(default_factory=list)

    # Template candidate
    is_template_candidate: bool = False
    template_confidence: float = 0.0  # 0-1

    def analyze_steps(self, steps: list):
        """Analyze recorded steps to extract patterns."""
        self.total_steps = len(steps)
        self.successful_steps = sum(1 for s in steps if s.get("status") == "completed")
        self.failed_steps = sum(1 for s in steps if s.get("status") == "failed")

        # Extract unique selectors
        for step in steps:
            selector = step.get("target_selector")
            if selector:
                self.selectors_used[step.get("action", "unknown")] = selector

        # Calculate template confidence
        if self.total_steps > 0:
            success_rate = self.successful_steps / self.total_steps
            consistency = len(set(s.get("action") for s in steps)) / max(len(steps), 1)
            self.template_confidence = round((success_rate * 0.7 + consistency * 0.3), 2)
            self.is_template_candidate = self.template_confidence > 0.8


class BrowserAutomationEngine:
    """High-level browser automation engine.
    
    Provides methods to execute automation jobs against FNO portals.
    In production, this wraps Playwright/Puppeteer subprocess calls.
    """

    def __init__(self, tenant_id: str, portal: str):
        self.tenant_id = tenant_id
        self.portal = portal
        self.active_sessions: dict = {}
        self.active_recordings: dict = {}

    async def create_session(self, browser_type: str = "headless_chrome") -> str:
        """Create a new browser session."""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        self.active_sessions[session_id] = {
            "browser_type": browser_type,
            "status": "active",
            "current_url": None,
            "started_at": datetime.utcnow(),
        }
        return session_id

    async def start_recording(self, job_id: str, session_id: str) -> ScreenRecording:
        """Start screen recording for a job."""
        recording = ScreenRecording(job_id=uuid.UUID(job_id))
        self.active_recordings[job_id] = recording
        return recording

    async def stop_recording(self, job_id: str) -> ScreenRecording:
        """Stop screen recording."""
        recording = self.active_recordings.get(job_id)
        if recording:
            recording.stop()
        return recording

    async def capture_mouse_action(self, job_id: str, action: MouseAction):
        """Record a mouse action."""
        recording = self.active_recordings.get(job_id)
        if recording:
            recording.add_mouse_action(action)

    async def take_screenshot(self, job_id: str, step_id: str, session_id: str,
                               full_page: bool = True, selector: Optional[str] = None) -> str:
        """Take a screenshot. Returns path to saved screenshot."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"screenshots/{job_id}/{step_id}_{timestamp}.png"
        # In production: actual screenshot via Playwright
        return filename

    async def extract_ui_elements(self, session_id: str, page_url: str) -> list:
        """Extract all interactable UI elements from current page."""
        # In production: use Playwright to query selectors
        return []

    async def execute_step(self, session_id: str, action: str, target: str,
                            value: Optional[str] = None) -> dict:
        """Execute a single automation step."""
        # In production: Playwright action execution
        return {"status": "completed", "action": action, "target": target}

    async def close_session(self, session_id: str):
        """Close a browser session."""
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["status"] = "closed"

    def analyze_process(self, job_id: str, steps: list) -> ProcessAnalysis:
        """Analyze a completed job to extract UI patterns and template candidates."""
        analysis = ProcessAnalysis(job_id=uuid.UUID(job_id), fno_portal=self.portal)
        analysis.analyze_steps(steps)
        return analysis

    def create_template_from_analysis(self, analysis: ProcessAnalysis) -> Optional[dict]:
        """Create an automation template from process analysis."""
        if not analysis.is_template_candidate:
            return None
        return {
            "name": f"Auto-template: {analysis.action_type} ({analysis.fno_portal})",
            "fno_portal": analysis.fno_portal,
            "job_type": analysis.action_type,
            "steps_template": [],  # Would be populated from analysis
            "selectors": analysis.selectors_used,
            "success_rate": analysis.successful_steps / max(analysis.total_steps, 1),
        }
