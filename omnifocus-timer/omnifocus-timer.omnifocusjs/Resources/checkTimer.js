/*{
  "type": "action",
  "targets": ["omnifocus"],
  "identifier": "checkTimer",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Show the current timer status.",
  "label": "Check Timer",
  "shortLabel": "Check Timer"
}*/
(() => {
  const action = new PlugIn.Action(async function (selection) {
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timerLib");
    const status = timerLib.getTimerStatus();

    let title = "";
    let message = "";

    if (status.status === "idle") {
      title = "No Timer Active";
      message = "No task is currently being timed.";
    } else {
      title = "Timer " + (status.status === "running" ? "Running" : "Paused");
      message = "Task: " + status.taskName;
      if (status.projectName) {
        message += "\nProject: " + status.projectName;
      }
      message += "\nElapsed: " + status.elapsedFormatted;
      message += "\nSessions: " + status.sessionCount;
      if (status.originalEstimate !== null && status.originalEstimate !== undefined && status.originalEstimate > 0) {
        message += "\nEstimate: " + timerLib.formatDuration(status.originalEstimate * 60000);
      }
    }

    const alert = new Alert(title, message);
    await alert.show();
  });

  action.validate = function (selection) {
    return true;
  };

  return action;
})();
