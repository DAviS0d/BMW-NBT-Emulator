precision lowp float;

varying mediump vec2 vTexCoord;
varying vec4 vColor;

uniform sampler2D tex0; 

void main()
{
    vec4 texColor = texture2D(tex0, vTexCoord);
    gl_FragColor.rgb = texColor.rrr * vColor.rgb;
	gl_FragColor.a = 1.;
}
