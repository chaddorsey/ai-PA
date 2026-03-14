/*{
  "type": "action",
  "targets": ["omnifocus"],
  "identifier": "startTimer",
  "author": "Chad Dorsey",
  "version": "1.0.0",
  "description": "Start timing the selected task. If another task is being timed, it will be stopped first.",
  "label": "Start Timer",
  "shortLabel": "Start Timer"
}*/
(() => {
  const action = new PlugIn.Action(async function (selection) {
    const timerLib = PlugIn.find("com.dorsey.omnifocus-timer").library("timerLib");
    const task = selection.tasks[0];
    const result = timerLib.startTimerOnTask(task.id.primaryKey);

    let title = "";
    let message = "";

    if (result.status === "started") {
      title = "Timer Started";
      message = "Now timing: " + result.taskName;
      if (result.projectName) {
        message += "\nProject: " + result.projectName;
      }
    } else if (result.status === "switched") {
      title = "Timer Switched";
      message = "Stopped: " + result.switchedFrom + "\nNow timing: " + result.taskName;
      if (result.projectName) {
        message += "\nProject: " + result.projectName;
      }
    } else if (result.status === "already_timing") {
      title = "Already Timing";
      message = "Already timing " + result.taskName + " (" + result.elapsedFormatted + ")";
    } else if (result.status === "resumed") {
      title = "Timer Resumed";
      message = "Resumed: " + result.taskName + " (" + result.elapsedFormatted + " elapsed)";
    } else {
      title = "Error";
      message = result.message || "Unknown error";
    }

    const alert = new Alert(title, message);
    await alert.show();
  });

  action.validate = function (selection) {
    return selection.tasks.length === 1;
  };

  return action;
})();
