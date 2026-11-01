

--
--
--
function hmi_ti2d_update_sportInstrument2D( view, model )

	-- Use for debug
    -- print("hmi_ti2d_update_sportInstrument2D: Entering")

	-- set every value to zero
	for i=1,40 do
		-- debug print
		--print(string.format("pointerVisibility%i", i ))

		hmi_setViewIntProperty( view, string.format("pointerVisibility%i", i ), 0 )
		hmi_setViewIntProperty( view, string.format("ScaleVisibility%i", i ), 0 )
	end
	-- manually set the last one.
	hmi_setViewIntProperty(view, hmi_getPropertyName("pointerVisibility41"),0 )

	-- get the values in order to calculate the scale in [0,1] for the pointer
	min_val = hmi_getModelValue( model, 0, 6 )
	max_val = hmi_getModelValue( model, 0, 7 )
	val_val = hmi_getModelValue( model, 0, 8 )
	
	-- get the values in order to calculate the scale in [0,1] for the pointer
	min_val_scale = hmi_getModelValue( model, 0, 9 )
	max_val_scale = hmi_getModelValue( model, 0, 10 )
	val_val_scale = hmi_getModelValue( model, 0, 11 )

	-- calc scale in [0,1] for the pointer
	scaled = val_val / (max_val - min_val)
	-- calc scale in [0,1] for the scale
	scaled_scale = val_val_scale / (max_val_scale - min_val_scale)

	-- calculate the pointer visibility property number
	activate_pointer = (scaled * 42)+0.5
	if activate_pointer >= 41 then activate_pointer = 41 end
	if activate_pointer < 1 then activate_pointer = 1 end
	
	-- calculate the pointer visibility property number for scale images
	activate_scale = (scaled_scale * 41)+0.5
	if activate_scale >= 41 then activate_scale = 40 end
	if activate_scale < 1 then activate_scale = 1 end

	-- calculate the scale visibility property number for scale images
	--activate_scale = activate_pointer - 1
	--if activate_scale <= 0 then activate_scale = 0 end

	-- activate all scales all the way to the pointer
	-- needle
	for i=1,activate_scale do
		hmi_setViewIntProperty( view, string.format("ScaleVisibility%i", i ), 1 )
	end


	hmi_setViewIntProperty( view, string.format("pointerVisibility%i", activate_pointer ), 1 )

	-- Use for debug
	-- print("hmi_ti2d_init_sportInstrument2D: Setting Property: ", new_property_value)

	--hmi_setViewIntProperty(view, hmi_getPropertyName("ProgressPosition"),new_property_value )

	-- Use for debug
	-- print("hmi_ti2d_init_sportInstrument2D: Setting Property: ")
end
