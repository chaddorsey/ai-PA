/*{
  "type": "action",
  "targets": ["omnifocus"],
  "author": "Chad Dorsey",
  "identifier": "com.dorsey.omnifocus-completion-watcher.startWatcher",
  "version": "1.0",
  "description": "Start the completion watcher polling timer.",
  "label": "Start Completion Watcher",
  "shortLabel": "Start Watcher"
}*/
(() => {
  const action = new PlugIn.Action(function (selection) {
    const lib = this.plugIn.library("watcherLib");
    lib.startWatcher();
    new Alert("Completion Watcher", "Watcher started.").show();
  });
  action.validate = function (selection) { return true; };
  return action;
})();
