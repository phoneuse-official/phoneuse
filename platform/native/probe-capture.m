#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <CoreMediaIO/CoreMediaIO.h>
int main(void) { @autoreleasepool {
 CMIOObjectPropertyAddress property={kCMIOHardwarePropertyAllowScreenCaptureDevices,kCMIOObjectPropertyScopeGlobal,kCMIOObjectPropertyElementMain};
 UInt32 enabled=1; OSStatus result=CMIOObjectSetPropertyData(kCMIOObjectSystemObject,&property,0,NULL,sizeof(enabled),&enabled);
 fprintf(stderr,"CMIO status: %d\n",result);
 [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:5]];
 AVCaptureDeviceDiscoverySession *discovery=[AVCaptureDeviceDiscoverySession discoverySessionWithDeviceTypes:@[AVCaptureDeviceTypeExternal] mediaType:AVMediaTypeMuxed position:AVCaptureDevicePositionUnspecified];
 NSMutableArray *rows=[NSMutableArray array];
 for (AVCaptureDevice *d in discovery.devices) [rows addObject:@{@"id":d.uniqueID,@"name":d.localizedName,@"connected":@(d.connected)}];
 NSData *data=[NSJSONSerialization dataWithJSONObject:rows options:NSJSONWritingPrettyPrinted error:nil];
 [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
 } return 0; }
