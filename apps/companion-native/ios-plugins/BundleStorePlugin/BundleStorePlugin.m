// BundleStorePlugin.m
// Capacitor plugin registration macro for BundleStorePlugin.

#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(BundleStorePlugin, "BundleStore",
  CAP_PLUGIN_METHOD(download, CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(getPath,  CAPPluginReturnPromise);
  CAP_PLUGIN_METHOD(list,     CAPPluginReturnPromise);
)
