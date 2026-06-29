require 'json'

package = JSON.parse(File.read(File.join(__dir__, 'package.json')))

Pod::Spec.new do |s|
  s.name = 'CapacitorAudioSession'
  s.version = package['version']
  s.summary = package['description']
  s.license = { :type => 'MIT' }
  s.homepage = 'https://github.com/local/capacitor-audio-session'
  s.authors = { 'Chad Dorsey' => 'cdorsey@concord.org' }
  s.source = { :git => '.', :tag => s.version.to_s }
  s.source_files = 'ios/Sources/**/*.{swift,h,m}'
  s.ios.deployment_target = '13.0'
  s.dependency 'Capacitor'
  s.swift_version = '5.1'
end
