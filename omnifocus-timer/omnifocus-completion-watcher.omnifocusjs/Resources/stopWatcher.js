/*{
  "type": "action",
  "targets": ["omnifocus"],
  "author": "Chad Dorsey",
  "identifier": "com.dorsey.omnifocus-completion-watcher.stopWatcher",
  "version": "1.0",
  "description": "Stop the completion watcher polling timer.",
  "label": "Stop Completion Watcher",
  "shortLabel": "Stop Watcher"
}*/
(() => {
  const action = new PlugIn.Action(function (selection) {
    const lib = this.plugIn.library("watcherLib");
    lib.stopWatcher();
    new Alert("Completion Watcher", "Watcher stopped.").show();
  });
  action.validate = function (selection) { return true; };
  return action;
})();
