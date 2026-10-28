import {test,expect} from 'vitest';
import {severity,safeText} from './semantics';
test('absence never implies healthy',()=>{expect(severity(null)).toBe('unknown');expect(severity({})).toBe('unknown')});
test('uses backend severity',()=>expect(severity({assessment:{severity:'red'}})).toBe('red'));
test('missing measurement remains unavailable',()=>expect(safeText(null)).toBe('unavailable'));
