/** ⓘ explanations, keyed by the label shown on the dashboard (tiles, table headers, key/value rows). */
export const INFO: Record<string, string> = {
  // Stat tiles
  'System offset':
    'How far this clock is from true time, as chrony estimates it. chrony corrects it gradually by running the clock slightly fast or slow, never by jumping.',
  'RMS offset':
    'Typical size of recent offsets (root mean square): the steady-state accuracy. "last" is the offset measured at the most recent clock update.',
  'PPS offset':
    "Offset between the GPS pulse-per-second edge and the system clock at the last sample. ± is chrony's error estimate for it.",
  Frequency:
    "How fast the Pi's crystal runs compared with true time, in parts per million (+ = fast; 1 ppm ≈ 86 ms/day). chrony compensates for it. Skew is the error bound on that estimate.",
  Stratum:
    'Hops from a reference clock. GPS/PPS is stratum 0, this server is 1 and its clients become 2. "ref" is the source currently selected.',
  'Satellites used':
    'Satellites in the fix / satellites tracked. HDOP and PDOP (dilution of precision) show how satellite geometry magnifies errors, horizontally and in 3D; below about 2 is good.',
  'NTP clients':
    'Distinct addresses that sent an NTP request in the last hour. req/s is the current request rate (averaged over 5 s); "since start" counts every address in chronyd\'s client log since it started.',
  'CPU temperature':
    'SoC temperature. The crystal\'s frequency follows temperature, so swings here show up in the frequency chart. "load" is the 1-minute load average.',

  // Time sources table
  Reach: 'How many of the last 8 polls got an answer. 8/8 means no recent losses.',
  Offset: 'Offset at the last sample: + means the local clock is ahead of this source.',
  '± error': 'Error margin of that sample (root distance): network delay plus the uncertainty the source reports.',
  'Std dev': "Jitter: the estimated standard deviation of this source's recent samples.",
  Freq: 'Estimated residual frequency of this source against the local clock, after correction. Close to 0 means stable.',

  // Server statistics
  'NTP dropped': 'NTP requests not answered because of rate limiting.',
  'NTS-KE accepted':
    'Network Time Security key-exchange connections (TLS on TCP 4460), which clients use to set up authenticated NTP.',
  'Authenticated NTP': 'NTP requests authenticated with NTS or a symmetric key.',
  'Interleaved NTP':
    'Requests in interleaved mode: each reply carries the exact transmit time of the previous one, for better accuracy.',
  'Kernel RX timestamps':
    'Responses that used a receive timestamp captured by the kernel, which is more precise than one taken in chronyd.',
  'Command requests': "chronyc monitoring queries, including this dashboard's own polling.",

  // System
  Load: '1, 5 and 15-minute load averages.',
  'Altitude (MSL)': "Height above mean sea level. ± is the receiver's vertical error estimate.",
  'Root delay / dispersion':
    'Network delay and accumulated error back to the stratum-1 server this clock syncs from; about 0 when locked to local PPS. Worst-case error ≤ delay/2 + dispersion.',
  'Update interval': 'Time between the last two clock updates by chrony.',
}
