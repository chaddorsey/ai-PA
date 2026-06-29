// LiveActivityPlugin.m
// Capacitor plugin registration macro for LiveActivityPlugin.
// Phase 2 — add this file to the App Xcode target when wiring Phase 2.

#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(LiveActivityPlugin, "LiveActivity",
  CAP_PLUGIN_METHOD(start,  CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(update, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(end,    CAPPluginReturnPromise);
)
