import React, { useState, useEffect, useRef, useMemo } from 'react';
import GridLayout from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import './ShoeRackLayoutManager.css';
import maleIcon from '../images/male.png';
// import femaleIcon from './images/female.png';

// Rack names are typed by humans ("500", " j1 ", "g1") but stored as "500" / "J1".
const normalizeRackQuery = (value) => String(value || '').trim().toUpperCase().replace(/\s+/g, '');

// Gender of the ONE occupant of a 2-compartment rack. Returns null when the rack
// has a single compartment, is empty, or is already full — i.e. only "half full"
// racks qualify. Used to seat a new joiner next to someone of the same gender.
const getSingleOccupantGender = (rack) => {
  if (String(rack.compartments) !== '2') return null;

  const hasFirst = !!(rack.compartment_1_employee || rack.compartment_1_external_personnel);
  const hasSecond = !!(rack.compartment_2_employee || rack.compartment_2_external_personnel);
  if (hasFirst === hasSecond) return null;

  return (hasFirst ? rack.gender_employee_1 : rack.employee_2_gender) || null;
};

const ShoeRackLayoutManager = () => {
  const [racks, setRacks] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [pathwayBlocks, setPathwayBlocks] = useState([]);
  const [layout, setLayout] = useState([]);
  const [leftEmployees, setLeftEmployees] = useState(new Set());
  const [genderMismatchItems, setGenderMismatchItems] = useState([]);
  const [genderMismatchSet, setGenderMismatchSet] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [containerWidth, setContainerWidth] = useState(window.innerWidth - 100);
  const [nextPathwayId, setNextPathwayId] = useState(0);
  const [isEditMode, setIsEditMode] = useState(false);
  const containerRef = useRef(null);



  

  // --- Assign Racks panel state ---
  const [showAssignPanel, setShowAssignPanel] = useState(false);
  const [assignMode, setAssignMode] = useState('by_date'); // 'by_date' | 'unassigned'
  const [assignDate, setAssignDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [joiners, setJoiners] = useState([]);
  const [assignedSet, setAssignedSet] = useState(new Set());
  const [loadingJoiners, setLoadingJoiners] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [assigningRows, setAssigningRows] = useState(new Set());
  const [swappingRows, setSwappingRows] = useState(new Set());

  // --- Clear Left Employees panel state ---
  const [showClearPanel, setShowClearPanel] = useState(false);
  const [clearItems, setClearItems] = useState([]);
  const [loadingClearItems, setLoadingClearItems] = useState(false);
  const [clearingRows, setClearingRows] = useState(new Set());
  const [clearedSet, setClearedSet] = useState(new Set());

  // --- Gender Mismatch panel state ---
  const [showGenderPanel, setShowGenderPanel] = useState(false);
  const [loadingGenderItems, setLoadingGenderItems] = useState(false);

  // --- Group highlight filter state ---
  const [groupOptions, setGroupOptions] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState('');
  const [groupMemberIds, setGroupMemberIds] = useState(new Set());
  const [loadingGroupMembers, setLoadingGroupMembers] = useState(false);

  // --- Rack search + half-occupied gender filter ---
  const [rackSearch, setRackSearch] = useState('');
  const [occupantGenderFilter, setOccupantGenderFilter] = useState('');

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        const width = containerRef.current.offsetWidth;
        setContainerWidth(width);
      }
    };

    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  // Toggle static when isEditMode changes
  useEffect(() => {
    if (layout.length === 0) return;

    const updatedLayout = layout.map(item => ({
      ...item,
      static: !isEditMode  // static = true in view mode, false in edit mode
    }));

    setLayout(updatedLayout);
  }, [isEditMode]);

  useEffect(() => {
    loadRackData();
    loadGroupOptions();
  }, []);

  const loadGroupOptions = async () => {
    try {
      const resp = await fetch('/api/resource/Group?fields=["name"]&limit_page_length=0', {
        headers: { Accept: 'application/json' }
      });
      const result = await resp.json();
      setGroupOptions((result.data || []).map(g => g.name));
    } catch (e) {
      console.error('Error loading groups:', e);
    }
  };

  useEffect(() => {
    if (!selectedGroup) {
      setGroupMemberIds(new Set());
      return;
    }
    setLoadingGroupMembers(true);
    fetch(`/api/method/customize_erpnext.api.api_endpoints.get_employees_by_group?custom_group=${encodeURIComponent(selectedGroup)}`, {
      headers: { Accept: 'application/json' }
    })
      .then(resp => resp.json())
      .then(result => {
        const data = result.message || {};
        setGroupMemberIds(new Set(data.employees || []));
      })
      .catch(e => console.error('Error loading group members:', e))
      .finally(() => setLoadingGroupMembers(false));
  }, [selectedGroup]);

  useEffect(() => {
    if (racks.length > 0) {
      createBlocksFromRacks(racks);
    }
  }, [racks]);

  const getCsrf = () =>
    window.frappe?.csrf_token || document.querySelector('meta[name="csrf-token"]')?.content;

  const applyJoinersResponse = (employees) => {
    const alreadyAssigned = new Set();
    setJoiners((employees || []).map(e => {
      if (e.already_assigned) alreadyAssigned.add(e.name);
      return {
        employee: e.name,
        employee_name: e.employee_name,
        gender: e.gender,
        department: e.department,
        rack_name: e.existing_rack_name || null,
        rack_display_name: e.existing_rack_display_name || null,
        compartment: e.existing_compartment || null,
        suggested: false,
        already_assigned: !!e.already_assigned
      };
    }));
    // Mark DB-assigned joiners as done so they show "Assigned" + their rack
    setAssignedSet(alreadyAssigned);
  };

  const loadTodayJoiners = async () => {
    setLoadingJoiners(true);
    setJoiners([]);
    setAssignedSet(new Set());
    try {
      const resp = await fetch(
        `/api/method/customize_erpnext.api.api_endpoints.get_today_joiners?date=${assignDate}`,
        { headers: { Accept: 'application/json' } }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.success) {
        applyJoinersResponse(data.employees);
      } else {
        alert(data.message || 'Failed to load joiners');
      }
    } catch (e) {
      alert('Error loading joiners: ' + e.message);
    } finally {
      setLoadingJoiners(false);
    }
  };

  const loadUnassignedEmployees = async () => {
    setLoadingJoiners(true);
    setJoiners([]);
    setAssignedSet(new Set());
    try {
      const resp = await fetch(
        '/api/method/customize_erpnext.api.api_endpoints.get_unassigned_employees',
        { headers: { Accept: 'application/json' } }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.success) {
        applyJoinersResponse(data.employees);
      } else {
        alert(data.message || 'Failed to load unassigned employees');
      }
    } catch (e) {
      alert('Error loading unassigned employees: ' + e.message);
    } finally {
      setLoadingJoiners(false);
    }
  };

  const suggestSlots = async () => {
    if (!joiners.length) return;
    setSuggesting(true);
    try {
      // Only ask suggestions for joiners who don't already have a rack
      const pendingJoiners = joiners.filter(j => !j.already_assigned);
      if (!pendingJoiners.length) { alert('All loaded joiners already have a rack.'); setSuggesting(false); return; }
      const payload = pendingJoiners.map(j => ({ name: j.employee, employee_name: j.employee_name, gender: j.gender }));
      const resp = await fetch(
        '/api/method/customize_erpnext.api.api_endpoints.suggest_shoe_racks',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: 'application/json',
            'X-Frappe-CSRF-Token': getCsrf()
          },
          body: `employees=${encodeURIComponent(JSON.stringify(payload))}`
        }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.success) {
        // Map suggestions back by employee id so already-assigned rows stay intact
        const byEmp = {};
        (data.suggestions || []).forEach(s => { if (s.employee) byEmp[s.employee] = s; });
        setJoiners(prev => prev.map(j => {
          if (j.already_assigned) return j;
          const s = byEmp[j.employee] || {};
          return { ...j, rack_name: s.rack_name || null, rack_display_name: s.rack_display_name || null, compartment: s.compartment || null, suggested: !!s.suggested };
        }));
      } else {
        alert(data.message || 'Failed to get suggestions');
      }
    } catch (e) {
      alert('Error suggesting: ' + e.message);
    } finally {
      setSuggesting(false);
    }
  };

  const assignSingle = async (employee, rack_name, compartment) => {
    setAssigningRows(prev => new Set([...prev, employee]));
    try {
      const resp = await fetch(
        '/api/method/customize_erpnext.api.api_endpoints.assign_shoe_racks',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: 'application/json',
            'X-Frappe-CSRF-Token': getCsrf()
          },
          body: `assignments=${encodeURIComponent(JSON.stringify([{ employee, rack_name, compartment }]))}`
        }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.assigned > 0) {
        setAssignedSet(prev => new Set([...prev, employee]));
      } else {
        alert((data.errors && data.errors[0]) || data.message || 'Assignment failed');
      }
    } catch (e) {
      alert('Error assigning: ' + e.message);
    } finally {
      setAssigningRows(prev => { const s = new Set(prev); s.delete(employee); return s; });
    }
  };

  // The suggested (or already assigned) rack is physically taken by someone
  // we cannot identify: flag that compartment as Unknown and move the
  // employee to another rack.
  const swapRack = async (row) => {
    if (!row.rack_name) return;
    const rackLabel = `${row.rack_display_name || row.rack_name} · C${row.compartment}`;
    if (!window.confirm(
      `Rack ${rackLabel} is already occupied by an unidentified person?\n\n` +
      `That compartment will be marked "Chưa xác định (Unknown)" and ` +
      `${row.employee_name} (${row.employee}) will be moved to another rack.`
    )) return;

    // Reserve every slot the other rows of this table are holding, so the
    // replacement never lands on a slot someone else is about to take.
    const exclude = joiners
      .filter(j => j.employee !== row.employee && j.rack_name)
      .map(j => ({ rack_name: j.rack_name, compartment: j.compartment }));

    setSwappingRows(prev => new Set([...prev, row.employee]));
    try {
      const resp = await fetch(
        '/api/method/customize_erpnext.api.api_endpoints.swap_shoe_rack',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: 'application/json',
            'X-Frappe-CSRF-Token': getCsrf()
          },
          body: `employee=${encodeURIComponent(row.employee)}`
            + `&rack_name=${encodeURIComponent(row.rack_name)}`
            + `&compartment=${encodeURIComponent(row.compartment)}`
            + `&exclude_slots=${encodeURIComponent(JSON.stringify(exclude))}`
        }
      );
      const result = await resp.json();
      const data = result.message || {};

      if (!data.success) {
        alert(data.message || 'Swap failed');
      }

      // Reflect whatever the server actually did, even on a partial failure
      // (old slot flagged but no free rack left).
      const stillHasRack = !!data.rack_name;
      setJoiners(prev => prev.map(j => {
        if (j.employee !== row.employee) return j;
        return {
          ...j,
          rack_name: data.rack_name || null,
          rack_display_name: data.rack_display_name || null,
          compartment: data.compartment || null,
          suggested: !!data.suggested,
          already_assigned: stillHasRack ? j.already_assigned : false,
          swapped_from: data.marked_unknown
            ? `${row.rack_display_name || row.rack_name} · C${row.compartment}`
            : j.swapped_from
        };
      }));

      setAssignedSet(prev => {
        const s = new Set(prev);
        if (data.assigned) s.add(row.employee);
        else if (data.released || !stillHasRack) s.delete(row.employee);
        return s;
      });

      if (data.success && window.frappe?.show_alert) {
        window.frappe.show_alert(
          { message: data.message, indicator: stillHasRack ? 'green' : 'orange' },
          5
        );
      } else if (data.success && !stillHasRack) {
        alert(data.message);
      }
    } catch (e) {
      alert('Error swapping rack: ' + e.message);
    } finally {
      setSwappingRows(prev => { const s = new Set(prev); s.delete(row.employee); return s; });
    }
  };

  const autoAssignAll = async () => {
    const pending = joiners.filter(r => r.rack_name && !assignedSet.has(r.employee));
    if (!pending.length) { alert('No pending suggestions to assign.'); return; }
    setAssigningRows(new Set(pending.map(r => r.employee)));
    try {
      const resp = await fetch(
        '/api/method/customize_erpnext.api.api_endpoints.assign_shoe_racks',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: 'application/json',
            'X-Frappe-CSRF-Token': getCsrf()
          },
          body: `assignments=${encodeURIComponent(JSON.stringify(pending.map(r => ({ employee: r.employee, rack_name: r.rack_name, compartment: r.compartment }))))}`
        }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.assigned > 0) {
        setAssignedSet(prev => new Set([...prev, ...pending.map(r => r.employee)]));
        if (window.frappe?.show_alert) {
          window.frappe.show_alert({ message: `Assigned ${data.assigned} employee(s)!`, indicator: 'green' }, 3);
        }
      }
      if (data.errors && data.errors.length) {
        alert(`Assigned ${data.assigned} of ${pending.length}.\n\nErrors:\n${data.errors.join('\n')}`);
      }
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setAssigningRows(new Set());
    }
  };

  const loadLeftEmployeesInRacks = async () => {
    setLoadingClearItems(true);
    setClearItems([]);
    setClearedSet(new Set());
    try {
      const resp = await fetch(
        '/api/method/customize_erpnext.api.api_endpoints.get_left_employees_in_racks',
        { headers: { Accept: 'application/json' } }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.success) {
        setClearItems(data.items || []);
      } else {
        alert(data.message || 'Failed to load data');
      }
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setLoadingClearItems(false);
    }
  };

  const clearRowKey = (item) => `${item.rack_name}:${item.compartment}`;

  const clearSingle = async (item) => {
    const key = clearRowKey(item);
    if (!window.confirm(`Clear ${item.employee_name} (${item.employee}) from rack ${item.rack_display_name} compartment ${item.compartment}?`)) return;
    setClearingRows(prev => new Set([...prev, key]));
    try {
      const resp = await fetch(
        '/api/method/customize_erpnext.api.api_endpoints.clear_left_employees_from_racks',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: 'application/json',
            'X-Frappe-CSRF-Token': getCsrf()
          },
          body: `items=${encodeURIComponent(JSON.stringify([{ rack_name: item.rack_name, compartment: item.compartment }]))}`
        }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.cleared > 0) {
        setClearedSet(prev => new Set([...prev, key]));
      } else {
        alert((data.errors && data.errors[0]) || data.message || 'Clear failed');
      }
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setClearingRows(prev => { const s = new Set(prev); s.delete(key); return s; });
    }
  };

  const clearAll = async () => {
    const pending = clearItems.filter(r => !clearedSet.has(clearRowKey(r)));
    if (!pending.length) { alert('No pending items to clear.'); return; }
    if (!window.confirm(`Clear ALL ${pending.length} left employee(s) from their racks? This cannot be undone.`)) return;
    const allKeys = new Set(pending.map(clearRowKey));
    setClearingRows(allKeys);
    try {
      const resp = await fetch(
        '/api/method/customize_erpnext.api.api_endpoints.clear_left_employees_from_racks',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: 'application/json',
            'X-Frappe-CSRF-Token': getCsrf()
          },
          body: `items=${encodeURIComponent(JSON.stringify(pending.map(r => ({ rack_name: r.rack_name, compartment: r.compartment }))))}`
        }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.cleared > 0) {
        setClearedSet(prev => new Set([...prev, ...pending.map(clearRowKey)]));
        if (window.frappe?.show_alert) {
          window.frappe.show_alert({ message: `Cleared ${data.cleared} rack slot(s)!`, indicator: 'green' }, 3);
        }
      }
      if (data.errors && data.errors.length) {
        alert(`Cleared ${data.cleared} of ${pending.length}.\n\nErrors:\n${data.errors.join('\n')}`);
      }
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setClearingRows(new Set());
    }
  };

  // Loads racks whose two occupants have different genders.
  // Used both for the icon markers on the grid and for the review panel list.
  const loadGenderMismatchRacks = async () => {
    setLoadingGenderItems(true);
    try {
      const resp = await fetch(
        '/api/method/customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.get_gender_mismatch_racks',
        { headers: { Accept: 'application/json' } }
      );
      const result = await resp.json();
      const data = result.message || {};
      if (data.success) {
        setGenderMismatchItems(data.items || []);
        setGenderMismatchSet(new Set((data.items || []).map(i => i.rack_name)));
      } else {
        console.error('Failed to load gender mismatch racks:', data.message);
      }
    } catch (e) {
      console.error('Error loading gender mismatch racks:', e.message);
    } finally {
      setLoadingGenderItems(false);
    }
  };

  const printLabels = () => {
    const toPrint = joiners.filter(r => r.rack_name && assignedSet.has(r.employee));
    if (!toPrint.length) { alert('No assigned employees to print labels for.'); return; }
    const html = `<!DOCTYPE html><html><head><title>Shoe Rack Labels</title>
<style>
  body{font-family:Arial,sans-serif;margin:16px}
  h3{margin-bottom:12px}
  .grid{display:flex;flex-wrap:wrap;gap:12px}
  .label{border:2px solid #333;border-radius:8px;padding:12px 16px;text-align:center;min-width:120px;page-break-inside:avoid}
  .rack{font-size:32px;font-weight:bold;color:#1d4ed8}
  .comp{font-size:12px;color:#6b7280;margin-top:2px}
  .name{font-size:13px;margin-top:6px}
  .id{font-size:11px;color:#9ca3af}
</style></head>
<body>
<h3>Shoe Rack Labels${assignMode === 'by_date' ? ' — ' + assignDate : ''}</h3>
<div class="grid">
  ${toPrint.map(r => `<div class="label">
    <div class="rack">${r.rack_display_name || r.rack_name}</div>
    <div class="comp">Compartment ${r.compartment}</div>
    <div class="name">${r.employee_name}</div>
    <div class="id">${r.employee}</div> 
  </div>`).join('')}
</div>
<script>window.onload=()=>window.print();</script>
</body></html>`;
    const win = window.open('', '_blank');
    if (win) { win.document.write(html); win.document.close(); }
  };

  const createBlocksFromRacks = (racksData, savedLayout = null, savedPathways = null) => {
    const newBlocks = [];
    const newLayout = [];
    const validBlockIds = [];

    // Step 1: Classify racks
    const letterRacks = []; // Racks with letters (A1, G3, J7, ...)
    const numberRacks = []; // Racks with numbers only (1, 2, 3, ...)

    racksData.forEach(rack => {
      const displayName = rack.rack_display_name || '';

      // Check for letters
      if (/[A-Za-z]/.test(displayName)) {
        letterRacks.push(rack);
      } else {
        numberRacks.push(rack);
      }
    });

    // console.log('Letter racks:', letterRacks.length);
    // console.log('Number racks:', numberRacks.length);
    // console.log('Male Icon:', maleIcon);

    // Step 2: Create blocks for number racks
    for (let i = 0; i < numberRacks.length; i += 16) {
      const blockRacks = numberRacks.slice(i, i + 16);

      // Pad if short
      while (blockRacks.length < 16) {
        blockRacks.push({
          name: `empty-num-${i}-${blockRacks.length}`,
          rack_display_name: '',
          status: null
        });
      }

      const blockId = `block-num-${i / 16}`;
      validBlockIds.push(blockId);

      newBlocks.push({
        id: blockId,
        racks: blockRacks,
        type: 'rack',
        category: 'number'
      });

      // Create layout item
      let layoutItem;
      if (savedLayout && savedLayout.find(item => item.i === blockId)) {
        layoutItem = {
          ...savedLayout.find(item => item.i === blockId),
          static: !isEditMode
        };
      } else {
        const blockIndex = i / 16;
        layoutItem = {
          i: blockId,
          x: blockIndex % 5,
          y: Math.floor(blockIndex / 5) * 1,
          w: 1,
          h: 1,
          minH: 1,
          maxH: 1,
          static: !isEditMode,
        };
      }
      newLayout.push(layoutItem);
    }

    // Step 3: Create blocks for letter racks
    const numberBlocksCount = Math.ceil(numberRacks.length / 16);

    for (let i = 0; i < letterRacks.length; i += 16) {
      const blockRacks = letterRacks.slice(i, i + 16);

      // Pad if short
      while (blockRacks.length < 16) {
        blockRacks.push({
          name: `empty-let-${i}-${blockRacks.length}`,
          rack_display_name: '',
          status: null
        });
      }

      const blockId = `block-let-${i / 16}`;
      validBlockIds.push(blockId);

      newBlocks.push({
        id: blockId,
        racks: blockRacks,
        type: 'rack',
        category: 'letter'
      });

      // Create layout item - placed below number blocks
      let layoutItem;
      if (savedLayout && savedLayout.find(item => item.i === blockId)) {
        layoutItem = {
          ...savedLayout.find(item => item.i === blockId),
          static: !isEditMode
        };
      } else {
        const blockIndex = i / 16;
        layoutItem = {
          i: blockId,
          x: blockIndex % 5,
          y: (numberBlocksCount * 1) + (Math.floor(blockIndex / 5) * 1), // Below number blocks
          w: 1,
          h: 1,
          minH: 1,
          maxH: 1,
          static: !isEditMode,
        };
      }
      newLayout.push(layoutItem);
    }

    // Step 4: Load pathway blocks
    if (savedPathways && savedPathways.length > 0) {
      setPathwayBlocks(savedPathways);

      savedPathways.forEach(pathway => {
        validBlockIds.push(pathway.id);

        if (savedLayout) {
          const pathwayLayoutItem = savedLayout.find(item => item.i === pathway.id);
          if (pathwayLayoutItem) {
            newLayout.push({
              ...pathwayLayoutItem,
              static: !isEditMode
            });
          }
        }
      });

      setNextPathwayId(Math.max(...savedPathways.map(p => parseInt(p.id.replace('pathway-', '')))) + 1);
    } else {
      setPathwayBlocks([]);
    }

    // Step 5: Clean orphan layout items
    const cleanedLayout = newLayout.filter(item => validBlockIds.includes(item.i));

    const removedItems = newLayout.length - cleanedLayout.length;
    if (removedItems > 0) {
      console.warn(`Removed ${removedItems} orphan layout items`);
    }

    // Sort layout
    cleanedLayout.sort((a, b) => {
      if (a.y !== b.y) return a.y - b.y;
      return a.x - b.x;
    });

    setBlocks(newBlocks);
    setLayout(cleanedLayout);
  };

  const loadRackData = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        '/api/resource/Shoe Rack?fields=["*"]&limit_page_length=0',
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
          }
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      const validRacks = (result.data || []).filter(rack => rack.rack_display_name);

      // Fetch Left employees
      try {
        const empResponse = await fetch(
          '/api/resource/Employee?filters=[["status","=","Left"]]&fields=["name"]&limit_page_length=0',
          {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json'
            }
          }
        );
        if (empResponse.ok) {
          const empResult = await empResponse.json();
          const leftEmps = new Set((empResult.data || []).map(emp => emp.name));
          setLeftEmployees(leftEmps);
        }
      } catch (empError) {
        console.error('Error fetching left employees:', empError);
      }

      // Fetch racks whose two occupants have different genders (for the icon markers)
      loadGenderMismatchRacks();

      validRacks.sort((a, b) => {
        const nameA = String(a.rack_display_name || '');
        const nameB = String(b.rack_display_name || '');
        return nameA.localeCompare(nameB, undefined, { numeric: true, sensitivity: 'base' });
      });

      setRacks(validRacks);
      await loadLayout(validRacks);

    } catch (error) {
      console.error('Error loading rack data:', error);
      setRacks([]);
      alert('Failed to load rack data. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  const loadLayout = async (racksData) => {
    try {
      const response = await fetch(
        '/api/resource/Shoe Rack Layout Settings/Shoe Rack Layout Settings',
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
          }
        }
      );

      if (response.ok) {
        const result = await response.json();

        if (result.data && result.data.layout_data) {
          const layoutData = JSON.parse(result.data.layout_data);
          const pathwayData = result.data.pathway_blocks ? JSON.parse(result.data.pathway_blocks) : null;
          createBlocksFromRacks(racksData, layoutData, pathwayData);

          // Force re-render after load
          // setTimeout(() => {
          //   setIsEditMode(true);
          //   setTimeout(() => {
          //     setIsEditMode(false);
          //   }, 100);
          // }, 100);

          return;
        }
      }

      createBlocksFromRacks(racksData);

    } catch (error) {
      console.error('Error loading layout:', error);
      createBlocksFromRacks(racksData);
    }
  };

  const saveLayout = async () => {
    setSaving(true);
    try {
      const csrfToken = window.frappe?.csrf_token || document.querySelector('meta[name="csrf-token"]')?.content;

      const response = await fetch(
        '/api/resource/Shoe Rack Layout Settings/Shoe Rack Layout Settings',
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Frappe-CSRF-Token': csrfToken
          },
          body: JSON.stringify({
            layout_data: JSON.stringify(layout),
            pathway_blocks: JSON.stringify(pathwayBlocks)
          })
        }
      );

      if (!response.ok) {
        if (response.status === 404) {
          const createResponse = await fetch(
            '/api/resource/Shoe Rack Layout Settings',
            {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Frappe-CSRF-Token': csrfToken
              },
              body: JSON.stringify({
                doctype: 'Shoe Rack Layout Settings',
                name: 'Shoe Rack Layout Settings',
                layout_data: JSON.stringify(layout),
                pathway_blocks: JSON.stringify(pathwayBlocks)
              })
            }
          );

          if (!createResponse.ok) {
            const errorData = await createResponse.json();
            throw new Error(errorData.message || 'Failed to create layout settings');
          }
        } else {
          const errorData = await response.json();
          throw new Error(errorData.message || 'Failed to save layout');
        }
      }

      setHasUnsavedChanges(false);

      if (window.frappe?.show_alert) {
        window.frappe.show_alert({
          message: 'Layout saved successfully!',
          indicator: 'green'
        }, 3);
      } else {
        alert('Layout saved successfully!');
      }

    } catch (error) {
      console.error('Error saving layout:', error);

      if (window.frappe?.show_alert) {
        window.frappe.show_alert({
          message: 'Failed to save layout: ' + error.message,
          indicator: 'red'
        }, 5);
      } else {
        alert('Failed to save layout: ' + error.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleLayoutChange = (newLayout) => {
    if (!isEditMode) return;
    setLayout(newLayout);
    setHasUnsavedChanges(true);
  };
  const handleRackClick = (rackName) => {
    window.location.href = `/app/shoe-rack/${rackName}`;
  };

  const handleAddPathway = () => {
    const newPathwayId = `pathway-${nextPathwayId}`;

    const newPathway = {
      id: newPathwayId,
      type: 'pathway',
      label: ''
    };

    const newLayoutItem = {
      i: newPathwayId,
      x: 0,
      y: Infinity,
      w: 2,           // Default width = 1 unit
      h: 0.5,         // Default height = 0.5 unit (smaller than rack)
      minW: 1,      // Minimum 0.5 unit (half a rack block)
      minH: 0.5,     // Minimum 0.25 unit (1/4 rack block)
    };

    setPathwayBlocks([...pathwayBlocks, newPathway]);
    setLayout([...layout, newLayoutItem]);
    setNextPathwayId(nextPathwayId + 1);
    setHasUnsavedChanges(true);
  };

  const handleDeleteBlock = (blockId) => {
    const isPathway = blockId.startsWith('pathway-');

    if (isPathway) {
      setPathwayBlocks(pathwayBlocks.filter(p => p.id !== blockId));
    }

    setLayout(layout.filter(item => item.i !== blockId));
    setHasUnsavedChanges(true);
  };

  const getStatusColor = (status) => {
    if (!status) return 'empty';

    const [occupied, total] = status.split('/').map(Number);

    if (occupied === 0) {
      return 'empty';
    } else if (occupied < total) {
      return 'partial';
    } else {
      return 'full';
    }
  };

  // Racks matching the typed rack name. Exact match wins over prefix match, so
  // typing "50" shows only rack 50 instead of 50 + 500 + 501...
  const searchMatchSet = useMemo(() => {
    const query = normalizeRackQuery(rackSearch);
    if (!query) return null;

    const exact = racks.filter(r => normalizeRackQuery(r.rack_display_name) === query);
    const hits = exact.length
      ? exact
      : racks.filter(r => normalizeRackQuery(r.rack_display_name).startsWith(query));

    return new Set(hits.map(r => r.name));
  }, [rackSearch, racks]);

  // Racks that are half full and whose lone occupant has the selected gender.
  const genderMatchSet = useMemo(() => {
    if (!occupantGenderFilter) return null;

    return new Set(
      racks
        .filter(r => getSingleOccupantGender(r) === occupantGenderFilter)
        .map(r => r.name)
    );
  }, [occupantGenderFilter, racks]);

  // Both filters apply together (AND). null means "no filter active".
  const filterMatchSet = useMemo(() => {
    if (!searchMatchSet) return genderMatchSet;
    if (!genderMatchSet) return searchMatchSet;
    return new Set([...searchMatchSet].filter(name => genderMatchSet.has(name)));
  }, [searchMatchSet, genderMatchSet]);

  // Bring the first match into view — a rack can easily be off-screen in a
  // layout this wide.
  useEffect(() => {
    if (!filterMatchSet || filterMatchSet.size === 0) return;

    const el = document.querySelector('.rack-item.filter-hit');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [filterMatchSet]);

  if (loading) {
    return (
      <div className="dashboard-container loading">
        <div className="loading-content">
          <div className="spinner"></div>
          <p>Loading rack data...</p>
        </div>
      </div>
    );
  }

  const allBlocks = [...blocks, ...pathwayBlocks];
  const isMobile = containerWidth < 650;

  // Sort blocks by layout order (y then x) for correct order on mobile
  const sortedBlocksForMobile = [...allBlocks].sort((a, b) => {
    const layoutA = layout.find(l => l.i === a.id);
    const layoutB = layout.find(l => l.i === b.id);
    if (!layoutA || !layoutB) return 0;
    if (layoutA.y !== layoutB.y) return layoutA.y - layoutB.y;
    return layoutA.x - layoutB.x;
  });

  // Renders the gender-mismatch icon on the LEFT of a rack cell.
  // The right side is already used by the "left employee" warning icon,
  // so this one lives on the opposite corner.
  const renderGenderWarningIcon = (rack, size) => {
    if (!genderMismatchSet.has(rack.name)) return null;
    const item = genderMismatchItems.find(i => i.rack_name === rack.name);
    const tooltip = item
      ? `Gender mismatch: ${item.compartment_1.name} (${item.compartment_1.gender}) & ${item.compartment_2.name} (${item.compartment_2.gender})`
      : 'Gender mismatch';
    return (
      <span
        className="gender-warning-icon"
        title={tooltip}
        style={{ backgroundImage: "url('https://res.cloudinary.com/dd6yp2m05/image/upload/v1784942239/gender-symbol_dtpkfp.png')", width: `${14}px`, height: `${14}px`, backgroundSize: 'contain', backgroundRepeat: 'no-repeat', position: 'absolute', bottom: `-3px`, left: `-3px`, opacity: 0.7, fontSize: `${size + 4}px`, zIndex: 10, borderRadius: '50%' }}
      >
        
      </span>
    );
  };

  return (
    <div className="dashboard-container">
      {/* Custom styling for the "Gender Mismatch" button — self-contained, no external CSS needed */}
      <style>{`
        .gender-mismatch-btn {
          position: relative;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 8px 16px;
          border: none;
          border-radius: 8px;
          background: linear-gradient(135deg, #f97316 0%, #db2777 100%);
          color: #fff;
          font-size: 13px;
          font-weight: 600;
          letter-spacing: 0.2px;
          cursor: pointer;
          box-shadow: 0 2px 6px rgba(219, 39, 119, 0.35);
          transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
        }
        .gender-mismatch-btn::before {
          content: '⚧';
          font-size: 15px;
          line-height: 1;
        }
        .gender-mismatch-btn:hover {
          transform: translateY(-1px);
          filter: brightness(1.08);
          box-shadow: 0 4px 10px rgba(219, 39, 119, 0.45);
        }
        .gender-mismatch-btn:active {
          transform: translateY(0);
          box-shadow: 0 2px 4px rgba(219, 39, 119, 0.35);
        }
      `}</style>

      <div className="dashboard-wrapper">
        <div className="dashboard-header">
          <div>
            <h1>Shoe Rack Dashboard</h1>
            <p className="total-racks">
              Total Racks: {racks.length} | Blocks: {blocks.length} | Pathways: {pathwayBlocks.length}
            </p>
          </div>
          <div className="header-actions">
            <button className="assign-btn" onClick={() => setShowAssignPanel(true)}>
              Assign Racks
            </button>
            <button
              className="clear-left-btn"
              onClick={() => { setShowClearPanel(true); loadLeftEmployeesInRacks(); }}
            >
              Clear Left Employees
            </button>
            <button
              className="gender-mismatch-btn"
              onClick={() => { setShowGenderPanel(true); loadGenderMismatchRacks(); }}
            >
              Gender Mismatch{genderMismatchItems.length > 0 ? ` (${genderMismatchItems.length})` : ''}
            </button>
            <button onClick={loadRackData} className="refresh-btn">
              <span className="refresh-icon">↻</span>
              Refresh
            </button>
          </div>
        </div>

        <div className="legend-section">
          <h2>Status Legend</h2>
          <div className="legend-items">
            <div className="legend-item">
              <div className="legend-box empty"></div>
              <span>Empty (0/1, 0/2)</span>
            </div>
            <div className="legend-item">
              <div className="legend-box partial"></div>
              <span>Partially Full (1/2)</span>
            </div>
            <div className="legend-item">
              <div className="legend-box full"></div>
              <span>Full (1/1, 2/2)</span>
            </div>
            <div className="legend-item">
              <div className="legend-box pathway"></div>
              <span>Pathway</span>
            </div>
          </div>
          <p className="drag-hint">
            💡 Drag corners/edges to resize height to fit content | Click ✖ to delete pathways
          </p>
          <p className="drag-hint">
            ⚠️ = employee has left the company (right corner) &nbsp;|&nbsp; <img src="https://res.cloudinary.com/dd6yp2m05/image/upload/v1784942239/gender-symbol_dtpkfp.png" style={{ width: '20px', height: '20px', objectFit: 'contain' }} alt="Gender Symbol" /> = 2 occupants of different genders in the same rack (left corner)
          </p>
        </div>

        {/* Rack Information */}
        <div className="rack-info-section">
          <h2>Rack Information</h2>
          <div className="info-grid">
            <div className="info-rack-card">
              <h3>📦 Capacity</h3>
              <ul>
                <li><strong>Rack 1-624:</strong> 2 compartments (2 users per rack)</li>
                <li><strong>Rack 625-732:</strong> 1 compartment (1 user per rack)</li>
              </ul>
            </div>

            <div className="info-rack-card">
              <h3>👥 Allocation</h3>
              <ul>
                {/* <li><strong>Rack 385-488:</strong> <img src={maleIcon} style={{width: '20px', height: '20px', objectFit: 'contain'}} alt="Male" /> Male </li> */}
                <li><strong>Rack J, G:</strong> Japanese & Guest</li>
                <li><strong>Rack A:</strong> External Employee</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="rack-section">
          <div className='flex justify-between items-center mb-4'>
            <h2>Rack Layout </h2>
            <div className="flex gap-2" style={{ alignItems: 'center' }}>
              {!isEditMode && (
                <div className="rack-search-control" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <label style={{ fontSize: '13px', color: '#6b7280' }}>Find Rack:</label>
                  <input
                    type="search"
                    className="rack-search-input"
                    value={rackSearch}
                    onChange={e => setRackSearch(e.target.value)}
                    placeholder="e.g. 500, J1"
                    title="Type a rack name to show only that rack"
                  />
                  {rackSearch && (
                    <span style={{ fontSize: '12px', color: searchMatchSet && searchMatchSet.size ? '#6b7280' : '#dc2626' }}>
                      {searchMatchSet ? `${searchMatchSet.size} rack(s)` : ''}
                    </span>
                  )}
                </div>
              )}
              {!isEditMode && (
                <div className="gender-filter-control" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <label style={{ fontSize: '13px', color: '#6b7280' }}>Half full, occupant is:</label>
                  <select
                    value={occupantGenderFilter}
                    onChange={e => setOccupantGenderFilter(e.target.value)}
                    className="group-filter-select"
                    title="2-compartment racks holding exactly one person of this gender"
                  >
                    <option value="">— Any —</option>
                    <option value="Female">Female</option>
                    <option value="Male">Male</option>
                  </select>
                  {occupantGenderFilter && (
                    <span style={{ fontSize: '12px', color: '#6b7280' }}>
                      {`${genderMatchSet ? genderMatchSet.size : 0} rack(s)`}
                    </span>
                  )}
                </div>
              )}
              {!isEditMode && (rackSearch || occupantGenderFilter) && (
                <button
                  className="rack-filter-clear-btn"
                  onClick={() => { setRackSearch(''); setOccupantGenderFilter(''); }}
                  title="Clear rack filters"
                >
                  ✕ Clear
                </button>
              )}
              {!isEditMode && (
                <div className="group-filter-control" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <label style={{ fontSize: '13px', color: '#6b7280' }}>Highlight Group:</label>
                  <select
                    value={selectedGroup}
                    onChange={e => setSelectedGroup(e.target.value)}
                    className="group-filter-select"
                  >
                    <option value="">— None —</option>
                    {groupOptions.map(g => (
                      <option key={g} value={g}>{g}</option>
                    ))}
                  </select>
                  {selectedGroup && (
                    <span style={{ fontSize: '12px', color: '#6b7280' }}>
                      {loadingGroupMembers ? 'Loading...' : `${groupMemberIds.size} employee(s)`}
                    </span>
                  )}
                </div>
              )}
              {/* Hide Edit button on mobile - desktop only */}
              {!isMobile && (
                !isEditMode ? (
                  <>
                    <button className='edit-btn' onClick={() => setIsEditMode(true)}>
                      Edit
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={handleAddPathway}
                      className="add-pathway-btn"
                    >
                      <span className="add-icon">➕</span>
                      Add Pathway
                    </button>
                    <button
                      className='save-btn'
                      onClick={async () => {
                        if (hasUnsavedChanges) {
                          await saveLayout();
                        }
                        setIsEditMode(false);
                      }}
                    >
                      ✓ OK
                    </button>
                    <button
                      className='refresh-btn'
                      onClick={() => {
                        if (hasUnsavedChanges) {
                          if (window.confirm('Discard all changes?')) {
                            loadRackData();
                            setIsEditMode(false);
                            setHasUnsavedChanges(false);
                          }
                        } else {
                          setIsEditMode(false);
                        }
                      }}
                    >
                      ✕ Cancel
                    </button>
                  </>
                )
              )}
            </div>
          </div>
          <div className="grid-container" ref={containerRef}>
            {!isEditMode ? (
              /* ===== VIEW MODE: flex-wrap auto-wraps (used for both desktop and mobile) ===== */
              <div className="mobile-rack-layout" style={{ justifyContent: 'center' }}>
                {sortedBlocksForMobile.map((block) => {
                  if (block.type === 'pathway') {
                    return (
                      <div key={block.id} className="mobile-pathway-item">
                        <div className="pathway-content">
                          <span className="pathway-label">{block.label || 'Pathway'}</span>
                        </div>
                      </div>
                    );
                  } else {
                    return (
                      <div key={block.id} className="mobile-rack-block-wrapper">
                        <div className="rack-grid">
                          {block.racks.map((rack) => {
                            const hasLeftEmp = leftEmployees.has(rack.compartment_1_employee) || leftEmployees.has(rack.compartment_2_employee);
                            const inGroup = !!selectedGroup && (groupMemberIds.has(rack.compartment_1_employee) || groupMemberIds.has(rack.compartment_2_employee));
                            const dimmedByGroup = !!selectedGroup && !inGroup;
                            const filterHit = !!filterMatchSet && filterMatchSet.has(rack.name);
                            const filterHidden = !!filterMatchSet && !filterHit;
                            const soloGender = getSingleOccupantGender(rack);
                            return (
                              <div
                                key={rack.name}
                                onDoubleClick={() => rack.rack_display_name && handleRackClick(rack.name)}
                                className={`rack-item ${getStatusColor(rack.status)} ${hasLeftEmp ? 'has-warning' : ''} ${inGroup ? 'group-highlight' : ''} ${dimmedByGroup ? 'group-dimmed' : ''} ${filterHit ? 'filter-hit' : ''} ${filterHidden ? 'filter-hidden' : ''}`}
                                title={rack.rack_display_name ? `${rack.rack_display_name} - ${rack.status || 'Empty'}${soloGender ? ` (1 free slot, current occupant: ${soloGender})` : ''}${hasLeftEmp ? ' (Contains a former employee)' : ''}${rack.do_not_auto_suggest ? ' (Do Not Auto Suggest)' : ''}` : ''}
                              >
                                {rack.rack_display_name}
                                {renderGenderWarningIcon(rack, 4)}
                                {hasLeftEmp && (
                                  <span
                                    className="warning-icon"
                                    title="Former employee"
                                    style={{ position: 'absolute', top: '-4px', right: '-4px', fontSize: '10px', zIndex: 10, background: 'white', borderRadius: '50%' }}
                                  >
                                    ⚠️
                                  </span>
                                )}

                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  }
                })}
              </div>
            ) : (
              /* ===== DESKTOP LAYOUT: react-grid-layout ===== */
              <GridLayout
                className="layout"
                layout={layout}
                cols={5}
                rowHeight={2}
                width={containerWidth}
                onLayoutChange={handleLayoutChange}
                compactType={null}
                preventCollision={true}
                isDraggable={true}
                isResizable={true}
                draggableHandle=".drag-handle"
                resizeHandles={['se', 'sw', 'ne', 'nw', 's', 'n', 'e', 'w']}
                margin={[8, 8]}
                containerPadding={[8, 8]}
              >
                {allBlocks.map((block) => {
                  if (block.type === 'pathway') {
                    return (
                      <div key={block.id} className="grid-item pathway-item">
                        {isEditMode && (
                          <button
                            className="delete-block-btn"
                            onClick={() => handleDeleteBlock
                              (block.id)}
                            title="Delete pathway"
                          >
                            ✖
                          </button>
                        )}
                        <div className="pathway-block">
                          {isEditMode && (
                            <div className="drag-handle">
                              <span className="drag-icon">⋮⋮</span>
                            </div>
                          )}
                          <div className="pathway-content">
                            <span className="pathway-label">{block.label}</span>
                          </div>
                        </div>
                      </div>
                    ); 
                  } else {
                    return ( 
                      <div key={block.id} className="grid-item">
                        <div className="rack-block">
                          {isEditMode && (
                            <div className="drag-handle">
                              <span className="drag-icon">⋮⋮</span>
                            </div>
                          )}
                          <div className="rack-grid">
                            {block.racks.map((rack) => {
                              const hasLeftEmp = leftEmployees.has(rack.compartment_1_employee) || leftEmployees.has(rack.compartment_2_employee);
                              return (
                                <div
                                  key={rack.name}
                                  onDoubleClick={() => rack.rack_display_name && handleRackClick(rack.name)}
                                  className={`rack-item ${getStatusColor(rack.status)} ${hasLeftEmp ? 'has-warning' : ''}`}
                                  title={rack.rack_display_name ? `${rack.rack_display_name} - ${rack.status || 'Empty'}${hasLeftEmp ? ' (Contains a former employee)' : ''}${rack.do_not_auto_suggest ? ' (Do Not Auto Suggest)' : ''}` : ''}
                                >
                                  {rack.rack_display_name}
                                  {renderGenderWarningIcon(rack, 5)}
                                  {hasLeftEmp && (
                                    <span
                                      className="warning-icon"
                                      title="Former employee"
                                      style={{ position: 'absolute', top: '-5px', right: '-5px', fontSize: '14px', zIndex: 10, background: 'white', borderRadius: '50%' }}
                                    >
                                      ⚠️
                                    </span>
                                  )}
                                  {rack.do_not_auto_suggest && <span className="no-suggest-dot" title="Do Not Auto Suggest" />}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    );
                  }
                })}
              </GridLayout>
            )}
          </div>
        </div>
      </div>

    {/* ===== ASSIGN RACKS PANEL ===== */}
    {showAssignPanel && (
      <div
        className="assign-overlay"
        onClick={e => e.target === e.currentTarget && setShowAssignPanel(false)}
      >
        <div className="assign-panel">
          <div className="assign-panel-header">
            <h2>Assign Shoe Racks</h2>
            <button className="assign-panel-close" onClick={() => setShowAssignPanel(false)}>✕</button>
          </div>

          <div className="assign-mode-tabs">
            <button
              className={`assign-mode-tab ${assignMode === 'by_date' ? 'active' : ''}`}
              onClick={() => { setAssignMode('by_date'); setJoiners([]); setAssignedSet(new Set()); }}
            >
              New Joiners (by Date)
            </button>
            <button
              className={`assign-mode-tab ${assignMode === 'unassigned' ? 'active' : ''}`}
              onClick={() => { setAssignMode('unassigned'); setJoiners([]); setAssignedSet(new Set()); }}
            >
              All Unassigned Employees
            </button>
          </div>

          <div className="assign-date-row">
            {assignMode === 'by_date' ? (
              <>
                <label>Joining Date:</label>
                <input
                  type="date"
                  className="assign-date-input"
                  value={assignDate}
                  onChange={e => setAssignDate(e.target.value)}
                />
                <button
                  className="assign-load-btn"
                  onClick={loadTodayJoiners}
                  disabled={loadingJoiners}
                >
                  {loadingJoiners ? 'Loading...' : 'Load Joiners'}
                </button>
              </>
            ) : (
              <>
                <span style={{ fontSize: '13px', color: '#6b7280' }}>
                  Every Active employee who does not currently occupy any rack.
                </span>
                <button
                  className="assign-load-btn"
                  onClick={loadUnassignedEmployees}
                  disabled={loadingJoiners}
                >
                  {loadingJoiners ? 'Loading...' : 'Load Unassigned Employees'}
                </button>
              </>
            )}
            {joiners.length > 0 && (
              <span style={{ fontSize: '13px', color: '#6b7280' }}>
                {joiners.length} employee{joiners.length !== 1 ? 's' : ''} found
                {assignedSet.size > 0 && ` · ${assignedSet.size} assigned`}
              </span>
            )}
          </div>

          <div className="assign-table-wrapper">
            {joiners.length === 0 ? (
              <p className="assign-empty">
                {loadingJoiners
                  ? 'Loading...'
                  : assignMode === 'by_date'
                    ? 'No new joiners found. Select a date and click "Load Joiners".'
                    : 'Click "Load Unassigned Employees" to list every Active employee without a rack.'}
              </p>
            ) : (
              <table className="assign-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Employee ID</th>
                    <th>Name</th>
                    <th>Gender</th>
                    <th>Department</th>
                    <th>Suggested Rack</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {joiners.map((row, idx) => {
                    const isDone = assignedSet.has(row.employee);
                    const isAssigning = assigningRows.has(row.employee);
                    const isSwapping = swappingRows.has(row.employee);
                    return (
                      <tr key={row.employee} className={isDone ? 'assign-row-done' : ''}>
                        <td>{idx + 1}</td>
                        <td>{row.employee}</td>
                        <td>{row.employee_name}</td>
                        <td>{row.gender || '—'}</td>
                        <td>{row.department || '—'}</td>
                        <td>
                          {row.rack_name ? (
                            <span className={`assign-rack-badge ${(row.suggested || row.already_assigned) ? 'suggested' : 'unmatched'}`}>
                              {row.rack_display_name || row.rack_name} · C{row.compartment}
                              {row.already_assigned ? ' ✓' : ''}
                            </span>
                          ) : (
                            <span className="assign-rack-none">—</span>
                          )}
                          {row.swapped_from && (
                            <div className="assign-swapped-from" title="Previous rack, now marked Unknown">
                              ⇄ was {row.swapped_from} (Unknown)
                            </div>
                          )}
                        </td>
                        <td>
                          {row.already_assigned
                            ? <span className="assign-status-done">Already assigned</span>
                            : isDone
                              ? <span className="assign-status-done">Assigned</span>
                              : <span className="assign-status-pending">Pending</span>
                          }
                        </td>
                        <td>
                          <div className="assign-row-actions">
                            {!isDone && row.rack_name && (
                              <button
                                className="assign-row-btn"
                                onClick={() => assignSingle(row.employee, row.rack_name, row.compartment)}
                                disabled={isAssigning || isSwapping}
                              >
                                {isAssigning ? '...' : 'Assign'}
                              </button>
                            )}
                            {row.rack_name && (
                              <button
                                className="assign-row-btn swap"
                                onClick={() => swapRack(row)}
                                disabled={isAssigning || isSwapping}
                                title="This rack is physically taken by an unidentified person: mark it Unknown and move this employee to another rack"
                              >
                                {isSwapping ? '...' : '⇄ Swap'}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div className="assign-panel-toolbar">
            <button
              className="assign-tool-btn suggest"
              onClick={suggestSlots}
              disabled={suggesting || joiners.length === 0}
            >
              {suggesting ? 'Suggesting...' : 'Suggest Slots'}
            </button>
            <button
              className="assign-tool-btn auto"
              onClick={autoAssignAll}
              disabled={assigningRows.size > 0 || !joiners.some(r => r.rack_name && !assignedSet.has(r.employee))}
            >
              {assigningRows.size > 0 ? 'Assigning...' : 'Auto Assign All'}
            </button>
            <button
              className="assign-tool-btn print"
              onClick={printLabels}
              disabled={assignedSet.size === 0}
            >
              Print Labels
            </button>
            <button
              className="assign-tool-btn"
              onClick={() => { setShowAssignPanel(false); loadRackData(); }}
            >
              Close &amp; Refresh
            </button>
          </div>
        </div>
      </div>
    )}

    {/* ===== CLEAR LEFT EMPLOYEES PANEL ===== */}
    {showClearPanel && (
      <div 
        className="assign-overlay"
        onClick={e => e.target === e.currentTarget && setShowClearPanel(false)}
      >
        <div className="assign-panel">
          <div className="assign-panel-header">
            <h2>Clear Left Employees — Resigned / Terminated</h2>
            <button className="assign-panel-close" onClick={() => setShowClearPanel(false)}>✕</button>
          </div>

          <div className="assign-date-row">
            {loadingClearItems ? (
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Loading...</span>
            ) : (
              <span style={{ fontSize: '13px', color: '#6b7280' }}>
                {clearItems.length} slot(s) still occupied by left employees
                {clearedSet.size > 0 && ` · ${clearedSet.size} cleared this session`}
              </span>
            )}
            <button
              className="assign-load-btn"
              onClick={loadLeftEmployeesInRacks}
              disabled={loadingClearItems}
            >
              {loadingClearItems ? 'Loading...' : 'Reload'}
            </button>
          </div>

          <div className="assign-table-wrapper">
            {clearItems.length === 0 ? (
              <p className="assign-empty">
                {loadingClearItems ? 'Loading...' : 'No left employees found in any rack.'}
              </p>
            ) : (
              <table className="assign-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Rack</th>
                    <th>C</th>
                    <th>Employee ID</th>
                    <th>Name</th>
                    <th>Department</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {clearItems.map((row, idx) => {
                    const key = clearRowKey(row);
                    const isDone = clearedSet.has(key);
                    const isClearing = clearingRows.has(key);
                    return (
                      <tr key={key} className={isDone ? 'assign-row-done' : ''}>
                        <td>{idx + 1}</td>
                        <td>
                          <span className="assign-rack-badge suggested">
                            {row.rack_display_name}
                          </span>
                        </td>
                        <td>{row.compartment}</td>
                        <td>{row.employee}</td>
                        <td>{row.employee_name}</td>
                        <td>{row.department || '—'}</td>
                        <td>
                          {isDone
                            ? <span className="assign-status-done">Cleared</span>
                            : <span className="clear-status-left">Left</span>
                          }
                        </td>
                        <td>
                          {!isDone && (
                            <button
                              className="clear-row-btn"
                              onClick={() => clearSingle(row)}
                              disabled={isClearing}
                            >
                              {isClearing ? '...' : 'Clear'}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div className="assign-panel-toolbar">
            <button
              className="assign-tool-btn clear-all-btn"
              onClick={clearAll}
              disabled={clearingRows.size > 0 || !clearItems.some(r => !clearedSet.has(clearRowKey(r)))}
            >
              {clearingRows.size > 0 ? 'Clearing...' : 'Clear All'}
            </button>
            <button
              className="assign-tool-btn"
              onClick={() => { setShowClearPanel(false); loadRackData(); }}
            >
              Close &amp; Refresh
            </button>
          </div>
        </div>
      </div>
    )}

    {/* ===== GENDER MISMATCH PANEL ===== */}
    {showGenderPanel && (
      <div
        className="assign-overlay"
        onClick={e => e.target === e.currentTarget && setShowGenderPanel(false)}
      >
        <div className="assign-panel">
          <div className="assign-panel-header">
            <h2>Gender Mismatch — Racks Shared by Different Genders</h2>
            <button className="assign-panel-close" onClick={() => setShowGenderPanel(false)}>✕</button>
          </div>

          <div className="assign-date-row">
            {loadingGenderItems ? (
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Loading...</span>
            ) : (
              <span style={{ fontSize: '13px', color: '#6b7280' }}>
                {genderMismatchItems.length} rack(s) shared by two different genders
              </span>
            )}
            <button
              className="assign-load-btn"
              onClick={loadGenderMismatchRacks}
              disabled={loadingGenderItems}
            >
              {loadingGenderItems ? 'Loading...' : 'Reload'}
            </button>
          </div>

          <div className="assign-table-wrapper">
            {genderMismatchItems.length === 0 ? (
              <p className="assign-empty">
                {loadingGenderItems ? 'Loading...' : 'No racks with a gender mismatch.'}
              </p>
            ) : (
              <table className="assign-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Rack</th>
                    <th>Compartment 1</th>
                    <th>Compartment 2</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {genderMismatchItems.map((row, idx) => (
                    <tr key={row.rack_name}>
                      <td>{idx + 1}</td>
                      <td>
                        <span className="assign-rack-badge suggested">
                          {row.rack_display_name || row.rack_name}
                        </span>
                      </td>
                      <td>{row.compartment_1.name} ({row.compartment_1.gender})</td>
                      <td>{row.compartment_2.name} ({row.compartment_2.gender})</td>
                      <td>
                        <button
                          className="assign-row-btn"
                          onClick={() => handleRackClick(row.rack_name)}
                        >
                          Open Rack
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="assign-panel-toolbar">
            <button
              className="assign-tool-btn"
              onClick={() => setShowGenderPanel(false)}
            >
              Close
            </button>
          </div>
        </div>
      </div>
    )}
  </div>
  );
};

// Note: assign panel lives inside dashboard-container so position:fixed overlay renders above everything

export default ShoeRackLayoutManager;