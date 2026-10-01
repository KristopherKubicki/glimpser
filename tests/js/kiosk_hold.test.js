import {createKioskHold} from '../../app/static/js/kiosk_hold.js';
import {jest} from '@jest/globals';
afterEach(()=>{jest.restoreAllMocks();localStorage.clear();});
test('online feed interruption is not described as offline',()=>{
 Object.defineProperty(navigator,'onLine',{configurable:true,value:true});
 const stage=document.createElement('div');document.body.append(stage);
 const hold=createKioskHold(stage,'test');
 hold.hold('Capture service unavailable');
 expect(stage.textContent).toContain('FEED INTERRUPTED');
 expect(stage.textContent).not.toContain('KIOSK OFFLINE');
 hold.recover();
});
test('browser offline is explicitly labeled',()=>{
 Object.defineProperty(navigator,'onLine',{configurable:true,value:false});
 const stage=document.createElement('div');document.body.append(stage);
 const hold=createKioskHold(stage,'test');
 hold.hold('No connection');
 expect(stage.textContent).toContain('KIOSK OFFLINE');
 hold.recover();
});
