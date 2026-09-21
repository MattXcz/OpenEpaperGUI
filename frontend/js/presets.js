// Built-in starter templates, modelled on the OpenEPaperLink drawcustom docs.

export const PRESETS = [
  {
    id: 'weather-forecast',
    name: 'Weather forecast strip',
    description: '8-column forecast with icons and temperatures, plus a 4-row list.',
    width: 296,
    height: 128,
    build() {
      const node = (id, type, props, extra = {}) => ({
        id, kind: 'element', type, props, ...extra,
      });
      return {
        name: 'Weather forecast strip',
        width: 296,
        height: 128,
        background: 'white',
        variables: [{ name: 'spacing', value: '49' }],
        nodes: [
          node('w-0', 'text', {
            value: ' ', x: 0, y: 0, size: 1, color: 'yellow',
          }),
          {
            id: 'w-forecast', kind: 'group', name: 'Hourly forecast',
            repeat: { enabled: true, var: 'i', count: 8, pre: [] },
            children: [
              node('w-t', 'text', {
                value: '{{ times[i] }}',
                x: '{{ 15 + i*spacing }}', y: 5, size: 10,
              }),
              node('w-i', 'icon', {
                value: "{{ icon_map.get(forecast[i].condition,'mdi:emoticon-happy') }}",
                x: '{{ 5 + i*spacing }}', y: 10, size: 50,
              }),
              node('w-temp', 'text', {
                value: '{{ temps[i] }}°',
                x: '{{ 20 + i*spacing }}', y: 58, size: 24, color: 'yellow',
              }),
            ],
          },
          {
            id: 'w-rows', kind: 'group', name: 'Detail rows',
            repeat: {
              enabled: true, var: 'i', count: 4,
              pre: ['offsets = [offset_0, offset_1, offset_2, offset_3, offset_4, offset_5]'],
            },
            children: [
              node('w-row', 'multiline', {
                value: '•{{nadpisy[i]}}|',
                delimiter: '|', offset_y: 20,
                x: 2, y: '{{ offsets[i] }}', size: 18,
              }),
            ],
          },
        ],
      };
    },
  },

  {
    id: 'sensor-dashboard',
    name: 'Sensor dashboard',
    description: 'Header, divider line, icon rows and battery progress bar.',
    width: 296,
    height: 128,
    build() {
      return {
        name: 'Sensor dashboard',
        width: 296,
        height: 128,
        background: 'white',
        variables: [
          { name: 'temp', value: "states('sensor.living_room_temperature')" },
          { name: 'hum', value: "states('sensor.living_room_humidity')" },
        ],
        nodes: [
          {
            id: 'd-title', kind: 'element', type: 'text',
            props: { value: 'Living Room', x: 6, y: 4, size: 26, color: 'black' },
          },
          {
            id: 'd-line', kind: 'element', type: 'line',
            props: { x_start: 6, x_end: 290, y_start: 36, y_end: 36, width: 2, fill: 'black' },
          },
          {
            id: 'd-i1', kind: 'element', type: 'icon',
            props: { value: 'mdi:thermometer', x: 8, y: 46, size: 24, fill: 'red' },
          },
          {
            id: 'd-t1', kind: 'element', type: 'text',
            props: { value: '{{ temp }} °C', x: 40, y: 46, size: 22, color: 'black' },
          },
          {
            id: 'd-i2', kind: 'element', type: 'icon',
            props: { value: 'mdi:water-percent', x: 8, y: 78, size: 24, fill: 'black' },
          },
          {
            id: 'd-t2', kind: 'element', type: 'text',
            props: { value: '{{ hum }} %', x: 40, y: 78, size: 22, color: 'black' },
          },
          {
            id: 'd-pb', kind: 'element', type: 'progress_bar',
            props: {
              x_start: 6, y_start: 108, x_end: 290, y_end: 124,
              progress: "{{ states('sensor.battery')|int(0) }}",
              fill: 'accent', outline: 'black', background: 'white',
              show_percentage: true,
            },
          },
        ],
      };
    },
  },

  {
    id: 'blank',
    name: 'Blank canvas',
    description: 'Empty 296×128 display, start from scratch.',
    width: 296,
    height: 128,
    build() {
      return {
        name: 'Blank canvas',
        width: 296,
        height: 128,
        background: 'white',
        variables: [],
        nodes: [],
      };
    },
  },
];