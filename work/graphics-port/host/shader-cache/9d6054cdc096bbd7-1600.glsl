precision lowp float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying mediump vec2 varCoord0;
varying mediump vec2 varCoord1;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;
uniform mediump float oparam4;
uniform mediump float oparam5;
uniform mediump float oparam6;
uniform mediump float oparam7;

// requires pre-multiplied rgb values
mediump vec4 blend( mediump vec4 dest, mediump vec4 src )
{
	mediump vec4 result;
	result.rgb = dest.rgb * (1.0-src.a) + src.rgb;
	
	// [performance] we don't need the correct alpha value
	// because we will not blend the background
	//result.a = clamp( dest.a + src.a, 0.0, 1.0 );
	result.a = 1.0;
	
	return result;
}

void main(){
	mediump vec4 color0 = texture2D(tex0, varCoord0);
	mediump vec4 color1 = texture2D(tex1, varCoord1);
	
	// require pre-multiplied alpha textures
	//color0.rgb = color0.rgb * color0.a;
	//color1.rgb = color1.rgb * color1.a;
	
	// blend horizon with lineament
	mediump vec4 blendedColor = blend( color0, color1 );

	gl_FragColor = blendedColor;
}