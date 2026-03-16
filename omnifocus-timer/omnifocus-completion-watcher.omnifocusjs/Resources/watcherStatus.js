/*{
  "type": "action",
  "targets": ["omnifocus"],
  "author": "Chad Dorsey",
  "identifier": "com.dorsey.omnifocus-completion-watcher.watcherStatus",
  "version": "1.0",
  "description": "Show completion watcher status.",
  "label": "Completion Watcher Status",
  "shortLabel": "Watcher Status"
}*/
(() => {
  const action = new PlugIn.Action(function (selection) {
    const lib = this.plugIn.library("watcherLib");
    const status = lib.getStatus();
    new Alert("Completion Watcher Status", status).show();
  });
  action.validate = function (selection) { return true; };
  return action;
})();
