import React, { useState, useMemo, useEffect } from 'react';
import {
  DndContext,
  useDraggable,
  DragOverlay,
  useSensor,
  useSensors,
  PointerSensor,
  KeyboardSensor,
} from '@dnd-kit/core';

// ===============================================
// 🎯 COMPLETE VERSION - With DB Integration
// Follows @dnd-kit docs pattern
// ===============================================

// Snap to grid modifier
function createSnapModifier(gridSize) {
  return (args) => {
    const { transform } = args;
    return {
      ...transform,
      x: Math.round(transform.x / gridSize) * gridSize,
      y: Math.round(transform.y / gridSize) * gridSize,
    };
  };
}

// Grid Background
function Grid({ size = 30 }) {
  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{
        backgroundImage: `
          repeating-linear-gradient(0deg, #e5e7eb 0px, #e5e7eb 1px, transparent 1px, transparent ${size}px),
          repeating-linear-gradient(90deg, #e5e7eb 0px, #e5e7eb 1px, transparent 1px, transparent ${size}px)
        `,
      }}
    />
  );
}

// Draggable Rack Block
function RackBlock({ rack }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: rack.id,
  });

  const style = {
    position: 'absolute',
    left: rack.position.x,
    top: rack.position.y,
    width: 200,
    height: 80,
    transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
    opacity: isDragging ? 0.5 : 1,
    cursor: isDragging ? 'grabbing' : 'grab',
    touchAction: 'none',
  };

  const statusColor = {
    '0/1': '#22c55e',
    '0/2': '#22c55e',
    '1/2': '#f97316',
    '1/1': '#ef4444',
    '2/2': '#ef4444',
  }[rack.status] || '#6b7280';

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className="bg-white rounded-lg border-2 border-gray-300 shadow-lg hover:border-blue-500 hover:shadow-xl transition-all"
    >
      <div className="p-3 h-full flex flex-col">
        <div className="flex items-center justify-between mb-1">
          <div className="text-xl font-bold text-gray-800">{rack.displayName}</div>
          <div
            className="px-2 py-0.5 rounded text-xs font-bold text-white"
            style={{ backgroundColor: statusColor }}
          >
            {rack.status}
          </div>
        </div>
        <div className="text-xs text-gray-600 flex-1">
          <div>{rack.gender === 'Male' ? '👨' : '👩'} {rack.gender}</div>
          <div>📦 {rack.compartments}C</div>
        </div>
        <div className="text-xs text-gray-400 mt-auto">
          ({rack.position.x}, {rack.position.y})
        </div>
      </div>
    </div>
  );
}

// Main Component
export default function RackLayoutManagerComplete() {
  const [gridSize, setGridSize] = useState(30);
  const [activeId, setActiveId] = useState(null);
  const [racks, setRacks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState(null);

  // Load racks from database on mount
  useEffect(() => {
    loadRacks();
  }, []);

  const loadRacks = async () => {
    try {
      setLoading(true);
      
      const response = await fetch('/api/method/customize_erpnext.api.api_endpoints.load_rack_positions');
      const data = await response.json();

      if (data.message && data.message.success) {
        setRacks(data.message.racks);
        console.log('✅ Loaded', data.message.racks.length, 'racks');
      } else {
        console.error('❌ Load failed:', data);
        // Use fallback data
        setRacks(getFallbackData());
      }
    } catch (error) {
      console.error('❌ Load error:', error);
      // Use fallback data
      setRacks(getFallbackData());
    } finally {
      setLoading(false);
    }
  };

  // Fallback data if API fails
  const getFallbackData = () => [
    { id: 'RACK-00001', name: 'RACK-00001', displayName: '1', status: '0/2', compartments: '2', gender: 'Male', position: { x: 60, y: 60 } },
    { id: 'RACK-00002', name: 'RACK-00002', displayName: '2', status: '1/2', compartments: '2', gender: 'Male', position: { x: 300, y: 60 } },
    { id: 'RACK-00003', name: 'RACK-00003', displayName: '3', status: '0/1', compartments: '1', gender: 'Female', position: { x: 540, y: 60 } },
    { id: 'J-00001', name: 'J-00001', displayName: 'J1', status: '2/2', compartments: '2', gender: 'Male', position: { x: 60, y: 180 } },
    { id: 'J-00002', name: 'J-00002', displayName: 'J2', status: '0/2', compartments: '2', gender: 'Female', position: { x: 300, y: 180 } },
    { id: 'G-00001', name: 'G-00001', displayName: 'G1', status: '0/1', compartments: '1', gender: 'Male', position: { x: 60, y: 300 } },
  ];

  const snapToGrid = useMemo(() => createSnapModifier(gridSize), [gridSize]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor)
  );

  const handleDragStart = (event) => {
    setActiveId(event.active.id);
  };

  const handleDragEnd = async (event) => {
    const { active, delta } = event;

    if (delta.x !== 0 || delta.y !== 0) {
      const updatedRacks = racks.map((rack) => {
        if (rack.id === active.id) {
          const newX = Math.max(0, rack.position.x + Math.round(delta.x / gridSize) * gridSize);
          const newY = Math.max(0, rack.position.y + Math.round(delta.y / gridSize) * gridSize);
          return { ...rack, position: { x: newX, y: newY } };
        }
        return rack;
      });

      setRacks(updatedRacks);

      // Save to DB
      const movedRack = updatedRacks.find((r) => r.id === active.id);
      if (movedRack) {
        await savePosition(movedRack.id, movedRack.position.x, movedRack.position.y);
      }
    }

    setActiveId(null);
  };

  const savePosition = async (rackId, x, y) => {
    try {
      setSaveStatus('saving');

      const response = await fetch('/api/method/customize_erpnext.api.api_endpoints.save_rack_positions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          positions: [{ rack_id: rackId, position_x: x, position_y: y }],
        }),
      });

      const data = await response.json();

      if (data.message && data.message.success) {
        setSaveStatus('saved');
        console.log(`✅ Saved ${rackId}: (${x}, ${y})`);
      } else {
        setSaveStatus('error');
        console.error('❌ Save failed:', data);
      }

      setTimeout(() => setSaveStatus(null), 2000);
    } catch (error) {
      console.error('❌ Save error:', error);
      setSaveStatus('error');
      setTimeout(() => setSaveStatus(null), 2000);
    }
  };

  const handleSaveAll = async () => {
    try {
      setSaveStatus('saving');

      const positions = racks.map((r) => ({
        rack_id: r.id,
        position_x: r.position.x,
        position_y: r.position.y,
      }));

      const response = await fetch('/api/method/customize_erpnext.api.api_endpoints.save_rack_positions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions }),
      });

      const data = await response.json();

      if (data.message && data.message.success) {
        setSaveStatus('saved');
        alert(`✅ Saved ${racks.length} positions!`);
      } else {
        setSaveStatus('error');
        alert('❌ Save failed!');
      }

      setTimeout(() => setSaveStatus(null), 2000);
    } catch (error) {
      console.error('❌ Save error:', error);
      setSaveStatus('error');
      alert('❌ Error: ' + error.message);
      setTimeout(() => setSaveStatus(null), 2000);
    }
  };

  const handleAutoArrange = () => {
    setRacks((items) =>
      items.map((rack, i) => ({
        ...rack,
        position: { x: 60 + (i % 3) * 240, y: 60 + Math.floor(i / 3) * 120 },
      }))
    );
  };

  const handleInitialize = async () => {
    if (!window.confirm('Initialize default positions for all racks?')) return;

    try {
      const response = await fetch('/api/method/customize_erpnext.api.api_endpoints.initialize_default_positions', {
        method: 'POST',
      });
      const data = await response.json();

      if (data.message && data.message.success) {
        alert(data.message.message);
        loadRacks();
      }
    } catch (error) {
      console.error('❌ Initialize error:', error);
      alert('Error: ' + error.message);
    }
  };

  const activeRack = racks.find((r) => r.id === activeId);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="text-2xl font-bold text-gray-700">Loading racks... ⏳</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-4 md:p-8">
      <div className="max-w-full mx-auto">
        {/* Header */}
        <div className="mb-4">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-800 mb-2">
            🗺️ Rack Layout Manager
          </h1>
          <p className="text-sm md:text-base text-gray-600">
            Snapping to {gridSize}px grid • {racks.length} racks • Auto-save enabled
          </p>
        </div>

        {/* Toolbar */}
        <div className="space-y-3 mb-4">
          {/* Grid Size */}
          <div className="bg-white rounded-lg shadow p-3 md:p-4">
            <div className="flex items-center space-x-4">
              <label className="text-sm font-semibold text-gray-700 whitespace-nowrap">
                Grid: {gridSize}px
              </label>
              <input
                type="range"
                min="20"
                max="50"
                value={gridSize}
                onChange={(e) => setGridSize(Number(e.target.value))}
                className="flex-1"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="bg-white rounded-lg shadow p-3 md:p-4">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={handleAutoArrange}
                className="px-3 py-2 bg-purple-500 hover:bg-purple-600 text-white rounded font-semibold text-sm"
              >
                📐 Arrange
              </button>
              <button
                onClick={handleSaveAll}
                disabled={saveStatus === 'saving'}
                className={`px-3 py-2 rounded font-semibold text-sm ${
                  saveStatus === 'saving'
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-green-500 hover:bg-green-600'
                } text-white`}
              >
                {saveStatus === 'saving' ? '⏳ Saving' : '💾 Save All'}
              </button>
              <button
                onClick={handleInitialize}
                className="px-3 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded font-semibold text-sm"
              >
                🔧 Initialize
              </button>
              <button
                onClick={loadRacks}
                className="px-3 py-2 bg-gray-500 hover:bg-gray-600 text-white rounded font-semibold text-sm"
              >
                🔄 Reload
              </button>
              {saveStatus === 'saved' && (
                <span className="px-3 py-2 text-green-600 font-semibold text-sm">✅ Saved!</span>
              )}
              {saveStatus === 'error' && (
                <span className="px-3 py-2 text-red-600 font-semibold text-sm">❌ Error!</span>
              )}
            </div>
          </div>
        </div>

        {/* Canvas */}
        <div className="bg-white rounded-xl shadow-2xl p-4 md:p-6">
          <div
            className="relative bg-gray-50 rounded-lg border-2 border-gray-300 overflow-auto"
            style={{ height: '600px' }}
          >
            <Grid size={gridSize} />

            <DndContext
              sensors={sensors}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
              modifiers={[snapToGrid]}
            >
              {racks.map((rack) => (
                <RackBlock key={rack.id} rack={rack} />
              ))}

              <DragOverlay>
                {activeRack && (
                  <div className="bg-blue-500 text-white rounded-lg p-3 shadow-2xl opacity-90">
                    <div className="font-bold">{activeRack.displayName}</div>
                    <div className="text-xs">{activeRack.status}</div>
                  </div>
                )}
              </DragOverlay>
            </DndContext>
          </div>
        </div>

        {/* Stats */}
        <div className="mt-4 bg-white rounded-lg shadow p-4">
          <div className="text-sm text-gray-600">
            <strong>💡 Tips:</strong> Drag any rack to move • Positions save automatically •
            Use "Initialize" for first-time setup
          </div>
        </div>
      </div>
    </div>
  );
}