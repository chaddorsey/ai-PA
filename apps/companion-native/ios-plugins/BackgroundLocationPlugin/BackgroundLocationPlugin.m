// BackgroundLocationPlugin.m
// Capacitor plugin registration macro for BackgroundLocationPlugin.
// Capacitor 6 reads this at runtime — no manual import in AppDelegate needed.

#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(BackgroundLocationPlugin, "BackgroundLocation",
  CAP_PLUGIN_METHOD(startWatch, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(clearWatch, CAPPluginReturnPromise);
)
