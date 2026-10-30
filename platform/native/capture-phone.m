#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <CoreMediaIO/CoreMediaIO.h>
#import <CoreImage/CoreImage.h>
#import <ImageIO/ImageIO.h>
#import <signal.h>
#import <unistd.h>
#import <pthread.h>
static pid_t originalParent;
static void *watchParent(void *unused) {
 while(getppid()==originalParent)sleep(1);
 _exit(0);
 return NULL;
}

@interface Receiver : NSObject <AVCaptureVideoDataOutputSampleBufferDelegate>
@property NSUInteger frames;
@property double first;
@property double last;
@property NSInteger width;
@property NSInteger height;
@property BOOL probe;
@property CIContext *context;
@property double quality;
@property double scale;
@property double fps;
@property double emittedAt;
@end
@implementation Receiver
- (void)captureOutput:(AVCaptureOutput *)output didOutputSampleBuffer:(CMSampleBufferRef)sample fromConnection:(AVCaptureConnection *)connection {
 @autoreleasepool {
  CVPixelBufferRef buffer=CMSampleBufferGetImageBuffer(sample);if(!buffer)return;
  double timestamp=CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample));
  if(self.frames==0)self.first=timestamp;self.last=timestamp;self.frames++;
  self.width=CVPixelBufferGetWidth(buffer);self.height=CVPixelBufferGetHeight(buffer);
  if(self.probe)return;
  if(timestamp-self.emittedAt < 1./self.fps-.002)return;self.emittedAt=timestamp;
  CIImage *image=[CIImage imageWithCVPixelBuffer:buffer];
  double scale=self.scale/100.;image=[image imageByApplyingTransform:CGAffineTransformMakeScale(scale,scale)];
  CGColorSpaceRef color=CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
  NSData *jpeg=[self.context JPEGRepresentationOfImage:image colorSpace:color options:@{(CIImageRepresentationOption)kCGImageDestinationLossyCompressionQuality:@(self.quality/100.)}];CGColorSpaceRelease(color);
  if(jpeg){uint32_t length=htonl((uint32_t)jpeg.length);if(fwrite(&length,4,1,stdout)!=1||fwrite(jpeg.bytes,1,jpeg.length,stdout)!=jpeg.length)_exit(0);fflush(stdout);}
 }
}
@end
int main(int argc,const char *argv[]) { @autoreleasepool {
 signal(SIGPIPE,SIG_DFL);
 originalParent=argc>4?(pid_t)atoi(argv[4]):getppid();
 if(originalParent<=1||getppid()!=originalParent)return 0;
 pthread_t watcher;pthread_create(&watcher,NULL,watchParent,NULL);pthread_detach(watcher);
 BOOL probe=argc>1&&strcmp(argv[1],"--probe")==0;
 NSString *identifier=argc>2?[NSString stringWithUTF8String:argv[2]]:@"";
 double seconds=argc>3?atof(argv[3]):10;
 CMIOObjectPropertyAddress property={kCMIOHardwarePropertyAllowScreenCaptureDevices,kCMIOObjectPropertyScopeGlobal,kCMIOObjectPropertyElementMain};UInt32 enabled=1;
 OSStatus status=CMIOObjectSetPropertyData(kCMIOObjectSystemObject,&property,0,NULL,sizeof(enabled),&enabled);
 if(status){fprintf(stderr,"screen discovery error %d\n",status);return 2;}
 AVCaptureDevice *device=nil;
 for(int i=0;i<20&&!device;i++){
  AVCaptureDeviceDiscoverySession *discovery=[AVCaptureDeviceDiscoverySession discoverySessionWithDeviceTypes:@[AVCaptureDeviceTypeExternal] mediaType:AVMediaTypeMuxed position:AVCaptureDevicePositionUnspecified];
  for(AVCaptureDevice *candidate in discovery.devices)if([candidate.uniqueID isEqualToString:identifier]){device=candidate;break;}
  if(!device)[[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.25]];
 }
 if(!device){fprintf(stderr,"selected USB screen unavailable\n");return 3;}
 NSError *error=nil;AVCaptureDeviceInput *input=[AVCaptureDeviceInput deviceInputWithDevice:device error:&error];
 if(!input){fprintf(stderr,"capture input: %s\n",error.localizedDescription.UTF8String);return 4;}
 AVCaptureSession *session=[AVCaptureSession new];
 if(![session canAddInput:input])return 5;[session addInput:input];
 AVCaptureVideoDataOutput *output=[AVCaptureVideoDataOutput new];output.alwaysDiscardsLateVideoFrames=YES;
 output.videoSettings=@{(id)kCVPixelBufferPixelFormatTypeKey:@(kCVPixelFormatType_32BGRA)};
 Receiver *receiver=[Receiver new];receiver.probe=probe;receiver.quality=45;receiver.scale=75;receiver.fps=60;receiver.context=[CIContext contextWithOptions:@{kCIContextCacheIntermediates:@NO}];
 dispatch_queue_t queue=dispatch_queue_create("phone.capture",DISPATCH_QUEUE_SERIAL);[output setSampleBufferDelegate:receiver queue:queue];
 if(![session canAddOutput:output])return 6;[session addOutput:output];[session startRunning];
 pid_t parent=originalParent;
 if(!probe)dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
  char line[1024];while(fgets(line,sizeof(line),stdin)){
   @autoreleasepool { NSData *data=[[NSString stringWithUTF8String:line] dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *settings=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if([settings isKindOfClass:[NSDictionary class]]){
     double fps=[settings[@"fps"] doubleValue],quality=[settings[@"quality"] doubleValue],scale=[settings[@"scale"] doubleValue];
     if(fps>=5&&fps<=60)receiver.fps=fps;if(quality>=10&&quality<=90)receiver.quality=quality;if(scale>=25&&scale<=100)receiver.scale=scale;
    }
   }
  }
 });
 NSDate *end=seconds>0?[NSDate dateWithTimeIntervalSinceNow:seconds]:nil;
 while(!end||[end timeIntervalSinceNow]>0){
  if(getppid()!=parent)_exit(0);
  if(!device.connected)break;
  [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.25]];
 }
 [session stopRunning];dispatch_sync(queue,^{});
 fprintf(stderr,"{\"frames\":%lu,\"fps\":%.2f,\"width\":%ld,\"height\":%ld}\n",(unsigned long)receiver.frames,receiver.last>receiver.first?(receiver.frames-1)/(receiver.last-receiver.first):0.,(long)receiver.width,(long)receiver.height);
 return receiver.frames?0:7;
} }
