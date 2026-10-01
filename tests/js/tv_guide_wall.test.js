import {jest} from '@jest/globals';
import {renderTvGuide, initTvGuideWall} from '../../app/static/js/tv_guide_wall.js';
beforeEach(()=>{document.body.innerHTML='<main id="tv-guide-wall"><a id="tv-guide-source-name"></a><span id="tv-guide-status"></span><span id="tv-guide-updated"></span><div id="tv-guide-grid"></div></main>';});
afterEach(()=>{jest.restoreAllMocks();delete global.fetch;});
test('fallback retains source attribution and local clock',()=>{
 renderTvGuide({source_name:'TVmaze',source_url:'https://www.tvmaze.com/',generated_at:'2026-09-25T15:00:00Z',cards:[{title:'Program',time:'08:00 PM CDT'}]});
 expect(document.querySelector('a').textContent).toBe('TVmaze');
 expect(document.querySelector('a').href).toBe('https://www.tvmaze.com/');
 expect(document.getElementById('tv-guide-updated').textContent).toContain('10:00');
 expect(document.getElementById('tv-guide-grid').textContent).toContain('08:00 PM CDT');
});
test('unavailable data response shows reason rather than generic HTTP failure',async()=>{
 global.fetch=jest.fn().mockResolvedValue({ok:false,status:502,json:async()=>({cards:[],message:'Program data unavailable; capture service is online.'})});
 await initTvGuideWall();
 expect(document.getElementById('tv-guide-grid').textContent).toContain('capture service is online');
 expect(document.getElementById('tv-guide-status').textContent).toBe('Lineup missing');
 expect(document.getElementById('tv-guide-wall').dataset.ready).toBe('1');
});
test('network failure remains visibly failed',async()=>{
 global.fetch=jest.fn().mockRejectedValue(new Error('Network unavailable'));
 await initTvGuideWall();
 expect(document.getElementById('tv-guide-status').textContent).toBe('Fetch failed');
});
