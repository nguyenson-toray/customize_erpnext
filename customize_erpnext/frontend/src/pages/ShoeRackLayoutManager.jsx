import React, { useState, useEffect, useRef } from 'react';
import GridLayout from 'react-grid-layout';
import { Resizable } from 'react-resizable';
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
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [containerWidth, setContainerWidth] = useState(window.innerWidth - 100);
  const [nextPathwayId, setNextPathwayId] = useState(0);
  const [isEditMode, setIsEditMode] = useState(false); 
  const containerRef = useRef(null);

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
     
            {/* <button 
              onClick={saveLayout} 
              className={`save-btn ${hasUnsavedChanges ? 'has-changes' : ''}`}
              disabled={saving || !hasUnsavedChanges}
            >
              <span className="save-icon">💾</span>
              {saving ? 'Saving...' : hasUnsavedChanges ? 'Save Layout' : 'Layout Saved'}
            </button> */}
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
            {!isEditMode ? (
              <>
                {/* <button 
                  onClick={handleAddPathway} 
                  className="add-pathway-btn"
                >
                  <span className="add-icon">➕</span>
                  Add Pathway
                </button> */}
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
                        loadRackData(); // Refresh lại data từ server
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
            )}
          </div>
        </div>
          <div className="grid-container" ref={containerRef}>
            <GridLayout
              className="layout"
              layout={layout}
              cols={5}
              rowHeight={2} // Giảm để resize mịn hơn
              width={containerWidth}
              onLayoutChange={handleLayoutChange}
              compactType={null}
              preventCollision={true}
              isDraggable={true}  
              isResizable={true} 
              draggableHandle=".drag-handle"  // GIỮ LẠI
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
                        onClick={() => handleDeleteBlock(block.id)}
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
                        {block.racks.map((rack) => (
                          <div
                            key={rack.name}
                            onDoubleClick={() => rack.rack_display_name && handleRackClick(rack.name)}
                            className={`rack-item ${getStatusColor(rack.status)}`}
                            title={rack.rack_display_name ? `${rack.rack_display_name} - ${rack.status || 'Empty'}` : ''}
                          >
                            {rack.rack_display_name}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              }
            })}
            </GridLayout>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ShoeRackLayoutManager;