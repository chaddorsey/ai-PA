// AudioSessionPlugin.m
// Capacitor plugin registration macro for AudioSessionPlugin.

#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(AudioSessionPlugin, "AudioSession",
  CAP_PLUGIN_METHOD(setMode,  CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(play,     CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(pause,    CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(resume,   CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(setRate,  CAPPluginReturnPromise);
)
