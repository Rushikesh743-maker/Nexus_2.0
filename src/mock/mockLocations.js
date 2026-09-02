/**
 * Mock mapped locations. Coordinates are approximate and fictional — the UI
 * never invents coordinates; everything plotted comes from here.
 * `entityIds` links locations to case entities; `lastActivityAt` feeds the
 * map date filter (events refine it at the service layer).
 */
export const mockLocations = [
  /* ---- inv-001 ---- */
  { id: 'loc-101', investigationId: 'inv-001', name: 'Galaxy Racing Lounge', type: 'business', lat: 18.5286, lng: 73.8553, address: 'East Street, Camp, Pune', notes: 'First-floor cabin used for late bookings after race meets.', entityIds: ['ent-101', 'ent-102'], lastActivityAt: '2026-08-16T21:30:00+05:30' },
  { id: 'loc-102', investigationId: 'inv-001', name: 'Silverline Turf Club', type: 'business', lat: 18.5236, lng: 73.8521, address: 'Racecourse Road, Agarkar Nagar, Pune', notes: 'Settlement gatherings observed post-race in the pavilion.', entityIds: ['ent-101', 'ent-103'], lastActivityAt: '2026-07-19T22:40:00+05:30' },
  { id: 'loc-103', investigationId: 'inv-001', name: 'Flat 4B, Kothrud', type: 'residence', lat: 18.5074, lng: 73.8077, address: 'Lane 4, Kothrud, Pune', notes: 'Reported venue of the August layer meeting.', entityIds: ['ent-101', 'ent-102'], lastActivityAt: '2026-08-16T20:00:00+05:30' },
  { id: 'loc-104', investigationId: 'inv-001', name: 'Cell tower 412, Pune Camp', type: 'communication', lat: 18.5312, lng: 73.8585, address: 'Clover Hill, Camp, Pune', notes: 'Tower serving settlement-call numbers on race days.', entityIds: ['ent-103', 'ent-105'], lastActivityAt: '2026-07-19T18:20:00+05:30' },
  { id: 'loc-105', investigationId: 'inv-001', name: 'NH-9 layby, Hadapsar', type: 'transit', lat: 18.5019, lng: 73.9296, address: 'NH-9, Hadapsar, Pune', notes: 'Crew vehicle observed idling before two race meets.', entityIds: ['ent-102'], lastActivityAt: '2026-08-02T17:50:00+05:30' },

  /* ---- inv-002 ---- */
  { id: 'loc-201', investigationId: 'inv-002', name: 'Warehouse 9, Bhiwandi', type: 'crime_scene', lat: 19.2967, lng: 73.0631, address: 'Survey 44, Bhiwandi, Thane', notes: 'Three of four intrusions; rear shutter entry each time.', entityIds: ['ent-201', 'ent-202'], lastActivityAt: '2026-06-24T03:10:00+05:30' },
  { id: 'loc-202', investigationId: 'inv-002', name: 'Wada Road service layby', type: 'transit', lat: 19.421, lng: 73.1283, address: 'Wada Road, Bhiwandi outskirts', notes: 'Tempo staging point before two incidents.', entityIds: ['ent-202'], lastActivityAt: '2026-06-24T03:40:00+05:30' },

  /* ---- inv-003 ---- */
  { id: 'loc-301', investigationId: 'inv-003', name: 'QuickTech Mobile Stores', type: 'business', lat: 19.018, lng: 72.8435, address: 'Shop 4, Kapadia Chambers, Dadar West, Mumbai', notes: 'Six mule kits activated at this counter in nine days.', entityIds: ['ent-303', 'ent-304', 'ent-305'], lastActivityAt: '2026-08-02T20:45:00+05:30' },
  { id: 'loc-302', investigationId: 'inv-003', name: 'Flat 12, Kurla West', type: 'residence', lat: 19.0697, lng: 72.8743, address: 'LBS Marg, Kurla West, Mumbai', notes: 'Address linked to the mule account holder.', entityIds: ['ent-302'], lastActivityAt: '2026-07-09T15:30:00+05:30' },
  { id: 'loc-303', investigationId: 'inv-003', name: 'Cyber café, Andheri East', type: 'surveillance', lat: 19.1136, lng: 72.8697, address: 'Station Road, Andheri East, Mumbai', notes: 'Net-banking sessions for the shell LLP traced here.', entityIds: ['ent-309'], lastActivityAt: '2026-08-14T12:10:00+05:30' },
  { id: 'loc-304', investigationId: 'inv-003', name: 'ATM cluster, BKC', type: 'transit', lat: 19.0669, lng: 72.8687, address: 'Bandra Kurla Complex, Mumbai', notes: 'Cash withdrawals preceding deposits into A/C ••3391.', entityIds: ['ent-302', 'ent-308'], lastActivityAt: '2026-08-14T13:05:00+05:30' },

  /* ---- inv-007 ---- */
  { id: 'loc-701', investigationId: 'inv-007', name: 'Godown A-7, MIDC Chakan', type: 'crime_scene', lat: 18.7606, lng: 73.8623, address: 'MIDC Phase 2, Chakan, Pune', notes: 'Search under warrant on 9 August; Panel 3 recovered.', entityIds: ['ent-703', 'ent-705'], lastActivityAt: '2026-08-09T01:40:00+05:30' },
  { id: 'loc-702', investigationId: 'inv-007', name: 'Weighbridge, NH-48 Chakan', type: 'transit', lat: 18.7461, lng: 73.8295, address: 'NH-48, Chakan, Pune', notes: 'Rendezvous cluster point on run nights.', entityIds: ['ent-702', 'ent-704'], lastActivityAt: '2026-08-27T03:20:00+05:30' },
  { id: 'loc-703', investigationId: 'inv-007', name: 'Market Yard, Gultekdi', type: 'business', lat: 18.4828, lng: 73.8591, address: 'Gultekdi Market Yard, Pune', notes: 'Suspected hand-off point to distributors.', entityIds: ['ent-701'], lastActivityAt: '2026-07-12T05:10:00+05:30' },
];

export default mockLocations;
