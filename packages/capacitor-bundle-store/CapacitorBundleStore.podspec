require 'json'

package = JSON.parse(File.read(File.join(__dir__, 'package.json')))

Pod::Spec.new do |s|
  s.name = 'CapacitorBundleStore'
  s.version = package['version']
  s.summary = package['description']
  s.license = { :type => 'MIT' }
  s.homepage = 'https://github.com/local/capacitor-bundle-store'
  s.authors = { 'Chad Dorsey' => 'cdorsey@concord.org' }
  s.source = { :git => '.', :tag => s.version.to_s }
  s.source_files = 'ios/Sources/BundleStorePlugin/**/*.{swift,h,m}'
  s.ios.deployment_target = '13.0'
  s.dependency 'Capacitor'
  s.dependency 'ZIPFoundation', '~> 0.9'
  s.swift_version = '5.1'
end
