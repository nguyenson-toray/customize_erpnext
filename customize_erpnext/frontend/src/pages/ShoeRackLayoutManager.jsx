import React, { useState, useEffect, useRef } from 'react';
import GridLayout from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import './ShoeRackLayoutManager.css';
import maleIcon from '../images/male.png';
// import femaleIcon from './images/female.png';

const ShoeRackLayoutManager = () => {
  const [racks, setRacks] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [pathwayBlocks, setPathwayBlocks] = useState([]);
  const [layout, setLayout] = useState([]);
  const [leftEmployees, setLeftEmployees] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [containerWidth, setContainerWidth] = useState(window.innerWidth - 100);
  const [nextPathwayId, setNextPathwayId] = useState(0);
  const [isEditMode, setIsEditMode] = useState(false);
  const containerRef = useRef(null);

  // --- Assign Racks panel state ---
  const [showAssignPanel, setShowAssignPanel] = useState(false);
  const [assignDate, setAssignDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [joiners, setJoiners] = useState([]);
  const [assignedSet, setAssignedSet] = useState(new Set());
  const [loadingJoiners, setLoadingJoiners] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [assigningRows, setAssigningRows] = useState(new Set());

  // --- Clear Left Employees panel state ---
  const [showClearPanel, setShowClearPanel] = useState(false);
  const [clearItems, setClearItems] = useState([]);
  const [loadingClearItems, setLoadingClearItems] = useState(false);
  const [clearingRows, setClearingRows] = useState(new Set());
  const [clearedSet, setClearedSet] = useState(new Set());

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

  // Thêm useEffect này để toggle static khi isEditMode thay đổi
  useEffect(() => {
    if (layout.length === 0) return;

    const updatedLayout = layout.map(item => ({
      ...item,
      static: !isEditMode  // static = true khi view mode, false khi edit mode
    }));

    setLayout(updatedLayout);
  }, [isEditMode]);

  useEffect(() => {
    loadRackData();
  }, []);

  useEffect(() => {
    if (racks.length > 0) {
      createBlocksFromRacks(racks);
    }
  }, [racks]);

  const getCsrf = () =>
    window.frappe?.csrf_token || document.querySelector('meta[name="csrf-token"]')?.content;

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
        setJoiners((data.employees || []).map(e => ({
          employee: e.name,
          employee_name: e.employee_name,
          gender: e.gender,
          department: e.department,
          rack_name: null,
          rack_display_name: null,
          compartment: null,
          suggested: false
        })));
      } else {
        alert(data.message || 'Failed to load joiners');
      }
    } catch (e) {
      alert('Error loading joiners: ' + e.message);
    } finally {
      setLoadingJoiners(false);
    }
  };

  const suggestSlots = async () => {
    if (!joiners.length) return;
    setSuggesting(true);
    try {
      const payload = joiners.map(j => ({ name: j.employee, employee_name: j.employee_name, gender: j.gender }));
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
        setJoiners(prev => prev.map((j, i) => {
          const s = (data.suggestions || [])[i] || {};
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
<h3>Shoe Rack Labels — ${assignDate}</h3>
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

    // ✅ BƯỚC 1: Phân loại racks
    const letterRacks = []; // Racks có chữ (A1, G3, J7, ...)
    const numberRacks = []; // Racks chỉ có số (1, 2, 3, ...)

    racksData.forEach(rack => {
      const displayName = rack.rack_display_name || '';

      // Check xem có chữ cái không
      if (/[A-Za-z]/.test(displayName)) {
        letterRacks.push(rack);
      } else {
        numberRacks.push(rack);
      }
    });

    console.log('Letter racks:', letterRacks.length);
    console.log('Number racks:', numberRacks.length);
    console.log('Male Icon:', maleIcon);

    // ✅ BƯỚC 2: Tạo blocks cho Number Racks (chỉ số)
    for (let i = 0; i < numberRacks.length; i += 16) {
      const blockRacks = numberRacks.slice(i, i + 16);

      // Padding nếu thiếu
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
        category: 'number' // ✅ Đánh dấu loại
      });

      // Tạo layout item
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

    // ✅ BƯỚC 3: Tạo blocks cho Letter Racks (có chữ)
    const numberBlocksCount = Math.ceil(numberRacks.length / 16);

    for (let i = 0; i < letterRacks.length; i += 16) {
      const blockRacks = letterRacks.slice(i, i + 16);

      // Padding nếu thiếu
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
        category: 'letter' // ✅ Đánh dấu loại
      });

      // Tạo layout item - Đặt phía dưới number blocks
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
          y: (numberBlocksCount * 1) + (Math.floor(blockIndex / 5) * 1), // Đặt dưới number blocks
          w: 1,
          h: 1,
          minH: 1,
          maxH: 1,
          static: !isEditMode,
        };
      }
      newLayout.push(layoutItem);
    }

    // ✅ BƯỚC 4: Load pathway blocks
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

    // ✅ BƯỚC 5: Clean orphan layout items
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

          // THÊM PHẦN NÀY - Force re-render sau khi load
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
      w: 2,           // Chiều rộng mặc định = 1 unit
      h: 0.5,         // Chiều cao mặc định = 0.5 unit (nhỏ hơn rack)
      minW: 1,      // ✅ Tối thiểu 0.5 unit (nửa rack block)
      minH: 0.5,     // ✅ Tối thiểu 0.25 unit (1/4 rack block)
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

  // Sắp xếp blocks theo thứ tự layout (y rồi x) để hiển thị đúng thứ tự trên mobile
  const sortedBlocksForMobile = [...allBlocks].sort((a, b) => {
    const layoutA = layout.find(l => l.i === a.id);
    const layoutB = layout.find(l => l.i === b.id);
    if (!layoutA || !layoutB) return 0;
    if (layoutA.y !== layoutB.y) return layoutA.y - layoutB.y;
    return layoutA.x - layoutB.x;
  });

  return (
    <div className="dashboard-container">
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
              <span>Pathway (Lối đi)</span>
            </div>
          </div>
          <p className="drag-hint">
            💡 Drag corners/edges to resize height to fit content | Click ✖ to delete pathways
          </p>
        </div>

        {/* ✅ THÊM PHẦN NÀY - Rack Information */}
        <div className="rack-info-section">
          <h2>Rack Information</h2>
          <div className="info-grid">
            <div className="info-card">
              <h3>📦 Capacity</h3>
              <ul>
                <li><strong>Rack 1-624:</strong> 2 compartments (2 users per rack)</li>
                <li><strong>Rack 625-732:</strong> 1 compartment (1 user per rack)</li>
              </ul>
            </div>

            <div className="info-card">
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
            <div className="flex gap-2">
              {/* Ẩn nút Edit trên mobile - chỉ hiện trên desktop */}
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
              /* ===== VIEW MODE: flex-wrap tự động rớt dòng (áp dụng cho cả desktop và mobile) ===== */
              <div className="mobile-rack-layout" style={{ justifyContent: 'center' }}>
                {sortedBlocksForMobile.map((block) => {
                  if (block.type === 'pathway') {
                    return (
                      <div key={block.id} className="mobile-pathway-item">
                        <div className="pathway-content">
                          <span className="pathway-label">{block.label || 'Lối đi'}</span>
                        </div>
                      </div>
                    );
                  } else {
                    return (
                      <div key={block.id} className="mobile-rack-block-wrapper">
                        <div className="rack-grid">
                          {block.racks.map((rack) => {
                            const hasLeftEmp = leftEmployees.has(rack.compartment_1_employee) || leftEmployees.has(rack.compartment_2_employee);
                            return (
                              <div
                                key={rack.name}
                                onDoubleClick={() => rack.rack_display_name && handleRackClick(rack.name)}
                                className={`rack-item ${getStatusColor(rack.status)} ${hasLeftEmp ? 'has-warning' : ''}`}
                                title={rack.rack_display_name ? `${rack.rack_display_name} - ${rack.status || 'Empty'}${hasLeftEmp ? ' (Có nhân viên nghỉ việc)' : ''}${rack.do_not_auto_suggest ? ' (Do Not Auto Suggest)' : ''}` : ''}
                              >
                                {rack.rack_display_name}
                                {hasLeftEmp && (
                                  <span
                                    className="warning-icon"
                                    title="Nhân viên nghỉ việc"
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
                                  title={rack.rack_display_name ? `${rack.rack_display_name} - ${rack.status || 'Empty'}${hasLeftEmp ? ' (Có nhân viên nghỉ việc)' : ''}${rack.do_not_auto_suggest ? ' (Do Not Auto Suggest)' : ''}` : ''}
                                >
                                  {rack.rack_display_name}
                                  {hasLeftEmp && (
                                    <span
                                      className="warning-icon"
                                      title="Nhân viên nghỉ việc"
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
            <h2>Assign Shoe Racks — New Joiners</h2>
            <button className="assign-panel-close" onClick={() => setShowAssignPanel(false)}>✕</button>
          </div>

          <div className="assign-date-row">
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
                {loadingJoiners ? 'Loading...' : 'No new joiners found. Select a date and click "Load Joiners".'}
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
                    return (
                      <tr key={row.employee} className={isDone ? 'assign-row-done' : ''}>
                        <td>{idx + 1}</td>
                        <td>{row.employee}</td>
                        <td>{row.employee_name}</td>
                        <td>{row.gender || '—'}</td>
                        <td>{row.department || '—'}</td>
                        <td>
                          {row.rack_name ? (
                            <span className={`assign-rack-badge ${row.suggested ? 'suggested' : 'unmatched'}`}>
                              {row.rack_display_name || row.rack_name} · C{row.compartment}
                            </span>
                          ) : (
                            <span className="assign-rack-none">—</span>
                          )}
                        </td>
                        <td>
                          {isDone
                            ? <span className="assign-status-done">Assigned</span>
                            : <span className="assign-status-pending">Pending</span>
                          }
                        </td>
                        <td>
                          {!isDone && row.rack_name && (
                            <button
                              className="assign-row-btn"
                              onClick={() => assignSingle(row.employee, row.rack_name, row.compartment)}
                              disabled={isAssigning}
                            >
                              {isAssigning ? '...' : 'Assign'}
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
  </div>
  );
};

// Note: assign panel lives inside dashboard-container so position:fixed overlay renders above everything

export default ShoeRackLayoutManager;