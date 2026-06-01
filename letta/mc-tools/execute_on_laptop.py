from typing import Dict, Any, Optional, List

def execute_on_laptop(command: str, use_applescript: bool = False) -> str:
    """
    Execute a command on the local laptop via SSH over Tailscale.
    Use this for filesystem operations, running scripts, or interacting with
    applications on the laptop.

    Bash examples:
      execute_on_laptop(command="ls ~/Dropbox")
      execute_on_laptop(command="cat ~/Documents/notes.txt")
      execute_on_laptop(command="open https://example.com")

    AppleScript examples:
      execute_on_laptop(command='tell application "Arc" to get URL of active tab of front window', use_applescript=True)
      execute_on_laptop(command='tell application "OmniFocus" to get name of every task of default document', use_applescript=True)
      execute_on_laptop(command='tell application "System Events" to get name of every process whose background only is false', use_applescript=True)

    Args:
        command: The bash command to execute, or AppleScript code if use_applescript is True
        use_applescript: If True, execute the command as AppleScript via osascript (default False)

    Returns:
        Command output (stdout) or error message
    """
    import subprocess

    laptop_ip = "100.95.213.46"
    ssh_user = "chaddorsey"
    ssh_opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-o", "LogLevel=ERROR",
    ]

    if use_applescript:
        remote_cmd = f"osascript -e {repr(command)}"
    else:
        remote_cmd = command

    try:
        result = subprocess.run(
            ["ssh"] + ssh_opts + [f"{ssh_user}@{laptop_ip}", remote_cmd],
            capture_output=True, text=True, timeout=120
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                output = f"{output}\nSTDERR: {stderr}" if output else stderr
            output += f"\n(exit code {result.returncode})"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "TIMEOUT: Command took longer than 120 seconds."
    except Exception as e:
        return f"ERROR: {str(e)}"
