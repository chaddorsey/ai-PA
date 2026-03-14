/*{
  "type": "action",
  "targets": ["omnifocus"],
  "identifier": "pauseTimer",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Pause the running timer, or resume it if already paused.",
  "label": "Pause Timer",
  "shortLabel": "Pause Timer"
}*/
(() => {
  const action = new PlugIn.Action(async function (selection) {
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timerLib");
    const status = timerLib.getTimerStatus();

    let result;
    if (status.status === "running") {
      result = timerLib.pauseTimer();
    } else if (status.status === "paused") {
      result = timerLib.resumeTimer();
    } else {
      const alert = new Alert("No Timer Active", "There is no timer to pause or resume.");
      await alert.show();
      return;
    }

    let title = "";
    let message = "";

    if (result.status === "paused" || result.status === "already_paused") {
      title = "Timer Paused";
      message = result.taskName + "\nElapsed: " + result.elapsedFormatted;
    } else if (result.status === "resumed" || result.status === "already_running") {
      title = "Timer Resumed";
      message = result.taskName + "\nElapsed: " + result.elapsedFormatted;
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
    return status.status === "running" || status.status === "paused";
  };

  return action;
})();
