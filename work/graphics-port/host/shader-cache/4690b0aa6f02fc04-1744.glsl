precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying mediump vec3 varCoord;
varying mediump float xCoord_dest;
varying mediump float left, right;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;

/*
oparam0: width complete
oparam1,2: alhpa falloff right and left
oparam3: highlight position
edge to link at textureCoordinate 0.5
*/

void main()
{
 	gl_FragColor = texture2D(tex0, varCoord.xy); 

	float highlightSize = 100.;
	float highlight = 1.-abs(clamp(xCoord_dest, -highlightSize, highlightSize)/highlightSize);
	float clip = clamp(xCoord_dest, 0., 1.);

	gl_FragColor.rgb += highlight;
	gl_FragColor.a *= max(clip,highlight);

	float test1 = float(varCoord.z < 0.5) * clamp( (1.-abs((varCoord.z * 2.) -1.))*left, 0., 1.);
	float test2 = float(varCoord.z >= 0.5) * clamp( (1.-abs((varCoord.z * 2.) -1.))*right, 0., 1.);
	gl_FragColor.a *= test1+test2;
}