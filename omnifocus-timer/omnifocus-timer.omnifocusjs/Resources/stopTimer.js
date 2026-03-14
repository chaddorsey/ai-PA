/*{
  "type": "action",
  "targets": ["omnifocus"],
  "identifier": "stopTimer",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Stop the active timer and save the session to the task note.",
  "label": "Stop Timer",
  "shortLabel": "Stop Timer"
}*/
(() => {
  const action = new PlugIn.Action(async function (selection) {
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timerLib");

    // Capture estimate before stopping (stop clears state)
    const preStatus = timerLib.getTimerStatus();
    const originalEstimate = preStatus.originalEstimate;

    const result = timerLib.stopTimer();

    let title = "";
    let message = "";

    if (result.status === "stopped") {
      title = "Timer Stopped";
      message = result.taskName + "\nTotal time: " + result.totalFormatted;
      if (originalEstimate !== null && originalEstimate !== undefined && originalEstimate > 0) {
        message += "\nEstimate was " + timerLib.formatDuration(originalEstimate * 60000);
        const diffMin = Math.round(result.totalElapsed / 60000) - originalEstimate;
        const sign = diffMin >= 0 ? "+" : "";
        message += " (" + sign + diffMin + " min)";
      }
    } else if (result.status === "idle") {
      title = "No Timer Active";
      message = "There is no timer running to stop.";
    } else {
      title = "Error";
      message = result.message || "Unknown error";
    }

    const alert = new Alert(title, message);
    await alert.show();
  });

  action.validate = function (selection) {
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timerLib");
    const status = timerLib.getTimerStatus();
    return status.status !== "idle";
  };

  return action;
})();
